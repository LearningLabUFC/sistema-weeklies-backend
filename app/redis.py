"""DEPRECATED — use app.core.redis.*"""

from app.core.redis.blacklist import (  # noqa: F401
    adicionar_token_blacklist,
    token_na_blacklist,
)
from app.core.redis.bruteforce import (  # noqa: F401
    aplicar_cooldown_bruteforce,
    limpar_tentativas,
    registrar_tentativa_falha,
    verificar_bloqueio_bruteforce,
)
from app.core.redis.connection import (  # noqa: F401
    encerrar_redis,
    get_redis,
    iniciar_redis,
)
from app.core.redis.otp import deletar_otp, salvar_otp, verificar_otp  # noqa: F401
from app.core.redis.rate_limit import (  # noqa: F401
    incrementar_rate_limit_email,
    incrementar_rate_limit_ip,
    verificar_rate_limit_email,
    verificar_rate_limit_ip,
)
