"""Anti Brute-force para verify-code."""
import logging
from app.config import settings
from app.core.redis.connection import get_redis
from app.core.redis.otp import _OTP_PREFIX

logger = logging.getLogger("uvicorn.error")

_BRUTEFORCE_PREFIX = "bruteforce:verify"
_COOLDOWN_PREFIX = "cooldown:verify"

async def verificar_bloqueio_bruteforce(email: str) -> bool:
    r = get_redis()
    chave = f"{_COOLDOWN_PREFIX}:{email}"
    return await r.exists(chave) == 1

async def registrar_tentativa_falha(email: str) -> int:
    r = get_redis()
    chave = f"{_BRUTEFORCE_PREFIX}:{email}"
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, settings.VERIFY_CODE_COOLDOWN_MINUTES * 60)
    resultados = await pipe.execute()
    return resultados[0]

async def aplicar_cooldown_bruteforce(email: str) -> None:
    r = get_redis()
    pipe = r.pipeline()
    pipe.delete(f"{_OTP_PREFIX}:{email}")
    pipe.delete(f"{_BRUTEFORCE_PREFIX}:{email}")
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
    r = get_redis()
    await r.delete(f"{_BRUTEFORCE_PREFIX}:{email}")
