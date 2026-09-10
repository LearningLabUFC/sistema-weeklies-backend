"""Blacklist JWT (logout / refresh rotation)."""
from app.core.redis.connection import get_redis

_BLACKLIST_PREFIX = "blacklist:jti"

async def adicionar_token_blacklist(jti: str, ttl_segundos: int) -> None:
    if ttl_segundos <= 0:
        return
    r = get_redis()
    await r.set(f"{_BLACKLIST_PREFIX}:{jti}", "1", ex=ttl_segundos)

async def token_na_blacklist(jti: str) -> bool:
    r = get_redis()
    return await r.exists(f"{_BLACKLIST_PREFIX}:{jti}") == 1
