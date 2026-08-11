"""
Módulo Redis — Conexão assíncrona e helpers para OTP.

Gerencia o pool de conexões com Redis e expõe funções
auxiliares para salvar, verificar e deletar códigos OTP.
"""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger("uvicorn.error")

# ── Pool de conexão (singleton) ──────────────────────────────

_redis_pool: aioredis.Redis | None = None


async def iniciar_redis() -> None:
    """Abre o pool de conexões com o Redis. Chamado no startup da app."""
    global _redis_pool
    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    # Verifica se a conexão está funcional
    await _redis_pool.ping()
    logger.info("✅ Redis conectado em %s", settings.REDIS_URL)


async def encerrar_redis() -> None:
    """Fecha o pool de conexões com o Redis. Chamado no shutdown da app."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("🔌 Redis desconectado.")


def get_redis() -> aioredis.Redis:
    """Retorna a instância ativa do Redis. Levanta erro se não iniciada."""
    if _redis_pool is None:
        raise RuntimeError("Redis não foi iniciado. Verifique o lifecycle da aplicação.")
    return _redis_pool


# ── Helpers OTP ──────────────────────────────────────────────

_OTP_PREFIX = "otp"


async def salvar_otp(email: str, codigo: str) -> None:
    """
    Salva um código OTP no Redis com TTL configurável.

    Chave: ``otp:{email}`` → valor: ``{codigo}``
    Se já existir um código para o e-mail, ele é sobrescrito.
    """
    r = get_redis()
    chave = f"{_OTP_PREFIX}:{email}"
    ttl_segundos = settings.OTP_EXPIRE_MINUTES * 60
    await r.set(chave, codigo, ex=ttl_segundos)
    logger.info(
        "🔑 OTP salvo para %s (expira em %d min)",
        email,
        settings.OTP_EXPIRE_MINUTES,
    )


async def verificar_otp(email: str, codigo: str) -> bool:
    """
    Compara o código recebido com o armazenado no Redis.

    Se o código estiver correto, a chave é **deletada** (uso único).
    Retorna True se válido, False caso contrário.
    """
    r = get_redis()
    chave = f"{_OTP_PREFIX}:{email}"
    codigo_salvo = await r.get(chave)

    if codigo_salvo is None or codigo_salvo != codigo:
        return False

    # Código correto — deletar para impedir reuso
    await r.delete(chave)
    return True


async def deletar_otp(email: str) -> None:
    """Remove manualmente o OTP de um e-mail (cleanup)."""
    r = get_redis()
    await r.delete(f"{_OTP_PREFIX}:{email}")


# ── Rate Limiting (forgot-password) ──────────────────────────

_RATE_LIMIT_PREFIX = "ratelimit:forgot"
_RATE_LIMIT_IP_PREFIX = "ratelimit:forgot:ip"


async def verificar_rate_limit_email(email: str) -> bool:
    """
    Verifica se o e-mail ainda pode solicitar um OTP.

    Retorna True se a requisição é PERMITIDA, False se bloqueada.
    Utiliza o padrão INCR + EXPIRE do Redis (sliding window counter).
    """
    r = get_redis()
    chave = f"{_RATE_LIMIT_PREFIX}:{email}"
    contagem = await r.get(chave)

    if contagem is not None and int(contagem) >= settings.FORGOT_PASSWORD_MAX_REQUESTS:
        return False
    return True


async def incrementar_rate_limit_email(email: str) -> None:
    """Incrementa o contador de requisições após gerar um OTP."""
    r = get_redis()
    chave = f"{_RATE_LIMIT_PREFIX}:{email}"
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, settings.FORGOT_PASSWORD_WINDOW_MINUTES * 60)
    await pipe.execute()


async def verificar_rate_limit_ip(ip: str) -> bool:
    """
    Verifica se o IP ainda pode solicitar OTPs (limite global).

    Limite: 10 requisições por janela de 15 minutos por IP.
    Retorna True se PERMITIDO, False se bloqueado.
    """
    r = get_redis()
    chave = f"{_RATE_LIMIT_IP_PREFIX}:{ip}"
    contagem = await r.get(chave)

    if contagem is not None and int(contagem) >= 10:
        return False
    return True


async def incrementar_rate_limit_ip(ip: str) -> None:
    """Incrementa o contador de requisições por IP."""
    r = get_redis()
    chave = f"{_RATE_LIMIT_IP_PREFIX}:{ip}"
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, settings.FORGOT_PASSWORD_WINDOW_MINUTES * 60)
    await pipe.execute()


# ── Anti Brute-force (verify-code) ───────────────────────────

_BRUTEFORCE_PREFIX = "bruteforce:verify"
_COOLDOWN_PREFIX = "cooldown:verify"


async def verificar_bloqueio_bruteforce(email: str) -> bool:
    """
    Verifica se o e-mail está em período de cooldown.

    Retorna True se BLOQUEADO, False se liberado.
    """
    r = get_redis()
    chave = f"{_COOLDOWN_PREFIX}:{email}"
    return await r.exists(chave) == 1


async def registrar_tentativa_falha(email: str) -> int:
    """
    Registra uma tentativa falha de verificação de OTP.

    Retorna o número atual de tentativas falhas.
    """
    r = get_redis()
    chave = f"{_BRUTEFORCE_PREFIX}:{email}"
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, settings.VERIFY_CODE_COOLDOWN_MINUTES * 60)
    resultados = await pipe.execute()
    return resultados[0]  # Valor retornado pelo INCR


async def aplicar_cooldown_bruteforce(email: str) -> None:
    """
    Deleta o OTP e aplica um cooldown de bloqueio.

    Chamado quando o limite de tentativas é atingido.
    """
    r = get_redis()
    pipe = r.pipeline()
    # Deletar o OTP para impedir tentativas futuras
    pipe.delete(f"{_OTP_PREFIX}:{email}")
    # Deletar o contador de tentativas
    pipe.delete(f"{_BRUTEFORCE_PREFIX}:{email}")
    # Aplicar cooldown
    pipe.set(
        f"{_COOLDOWN_PREFIX}:{email}",
        "1",
        ex=settings.VERIFY_CODE_COOLDOWN_MINUTES * 60,
    )
    await pipe.execute()
    logger.info(
        "🚫 Cooldown aplicado para %s (%d min)",
        email,
        settings.VERIFY_CODE_COOLDOWN_MINUTES,
    )


async def limpar_tentativas(email: str) -> None:
    """Limpa o contador de tentativas falhas após verificação bem-sucedida."""
    r = get_redis()
    await r.delete(f"{_BRUTEFORCE_PREFIX}:{email}")
