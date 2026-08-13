"""
Dependências reutilizáveis — Autenticação.

Fornece o dependency `get_current_user` que extrai e valida
o token JWT do header Authorization e retorna o usuário
correspondente do banco de dados.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.security import decodificar_token

oauth2_scheme = HTTPBearer()


async def get_current_user(
    auth: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency do FastAPI que:
    1. Extrai o Bearer token do header Authorization.
    2. Decodifica e valida o JWT.
    3. Busca o usuário no banco pelo 'sub' (ID) do payload.
    4. Verifica se o token foi emitido após a última troca de senha.
    5. Levanta 401 se qualquer etapa falhar.
    """
    credenciais_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de acesso ausente ou inválido.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = auth.credentials
    payload = decodificar_token(token)
    if payload is None:
        raise credenciais_exception

    # Apenas tokens de acesso são válidos aqui (não refresh tokens)
    if payload.get("tipo") != "acesso":
        raise credenciais_exception

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credenciais_exception

    usuario = db.query(User).filter(User.id == user_id).first()
    if usuario is None or usuario.status.nome != "ativo":
        raise credenciais_exception

    # Invalidar tokens emitidos antes da última troca de senha
    # JWT iat tem precisão de segundos, enquanto o banco tem microsegundos.
    # Truncamos o timestamp do banco para evitar falso-positivo no mesmo segundo.
    iat = payload.get("iat")
    if iat and usuario.senha_atualizada_em:
        token_emitido_em = datetime.fromtimestamp(iat, tz=timezone.utc)
        senha_atualizada = usuario.senha_atualizada_em.replace(microsecond=0)
        if token_emitido_em < senha_atualizada:
            raise credenciais_exception

    return usuario


def require_role(allowed_roles: list[str]):
    """
    Dependency factory que verifica se o usuário autenticado possui
    um dos cargos (roles) permitidos.
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.role or current_user.role.nome not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado. Nível de permissão insuficiente.",
            )
        return current_user
    return role_checker
