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
