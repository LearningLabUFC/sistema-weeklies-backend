"""Módulo Redis — Conexão assíncrona e pool."""
import logging
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger("uvicorn.error")

_redis_pool: aioredis.Redis | None = None

async def iniciar_redis() -> None:
    global _redis_pool
    if _redis_pool is not None:
        try:
            await _redis_pool.ping()
            return
        except (ConnectionError, TimeoutError, aioredis.RedisError):
            _redis_pool = None

    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    await _redis_pool.ping()
    logger.info("✅ Redis conectado em %s", settings.REDIS_URL)

async def encerrar_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("🔌 Redis desconectado.")

def get_redis() -> aioredis.Redis:
    if _redis_pool is None:
        raise RuntimeError("Redis não foi iniciado. Verifique o lifecycle da aplicação.")
    return _redis_pool
