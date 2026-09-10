"""Rate Limiting para forgot-password e IP."""
from app.config import settings
from app.core.redis.connection import get_redis

_RATE_LIMIT_PREFIX = "ratelimit:forgot"
_RATE_LIMIT_IP_PREFIX = "ratelimit:forgot:ip"

async def verificar_rate_limit_email(email: str) -> bool:
    r = get_redis()
    chave = f"{_RATE_LIMIT_PREFIX}:{email}"
    contagem = await r.get(chave)
    return not (contagem is not None and int(contagem) >= settings.FORGOT_PASSWORD_MAX_REQUESTS)

async def incrementar_rate_limit_email(email: str) -> None:
    r = get_redis()
    chave = f"{_RATE_LIMIT_PREFIX}:{email}"
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, settings.FORGOT_PASSWORD_WINDOW_MINUTES * 60)
    await pipe.execute()

async def verificar_rate_limit_ip(ip: str) -> bool:
    r = get_redis()
    chave = f"{_RATE_LIMIT_IP_PREFIX}:{ip}"
    contagem = await r.get(chave)
    return not (contagem is not None and int(contagem) >= settings.FORGOT_PASSWORD_IP_MAX_REQUESTS)

async def incrementar_rate_limit_ip(ip: str) -> None:
    r = get_redis()
    chave = f"{_RATE_LIMIT_IP_PREFIX}:{ip}"
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, settings.FORGOT_PASSWORD_WINDOW_MINUTES * 60)
    await pipe.execute()
