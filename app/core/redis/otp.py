"""Helpers OTP para o Redis."""

import logging

from app.config import settings
from app.core.redis.connection import get_redis

logger = logging.getLogger("uvicorn.error")

_OTP_PREFIX = "otp"


async def salvar_otp(email: str, codigo: str) -> None:
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
    r = get_redis()
    chave = f"{_OTP_PREFIX}:{email}"
    codigo_salvo = await r.get(chave)

    if codigo_salvo is None or codigo_salvo != codigo:
        return False

    await r.delete(chave)
    return True


async def deletar_otp(email: str) -> None:
    r = get_redis()
    await r.delete(f"{_OTP_PREFIX}:{email}")
