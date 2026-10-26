"""Pacote Redis — re-exporta funções para facilitar imports."""

from app.core.redis.blacklist import adicionar_token_blacklist, token_na_blacklist
from app.core.redis.bruteforce import (
    aplicar_cooldown_bruteforce,
    limpar_tentativas,
    registrar_tentativa_falha,
    verificar_bloqueio_bruteforce,
)
from app.core.redis.connection import encerrar_redis, get_redis, iniciar_redis
from app.core.redis.otp import deletar_otp, salvar_otp, verificar_otp
from app.core.redis.rate_limit import (
    incrementar_rate_limit_email,
    incrementar_rate_limit_ip,
    verificar_rate_limit_email,
    verificar_rate_limit_ip,
)

__all__ = [
    "adicionar_token_blacklist",
    "aplicar_cooldown_bruteforce",
    "deletar_otp",
    "encerrar_redis",
    "get_redis",
    "incrementar_rate_limit_email",
    "incrementar_rate_limit_ip",
    "iniciar_redis",
    "limpar_tentativas",
    "registrar_tentativa_falha",
    "salvar_otp",
    "token_na_blacklist",
    "verificar_bloqueio_bruteforce",
    "verificar_otp",
    "verificar_rate_limit_email",
    "verificar_rate_limit_ip",
]
