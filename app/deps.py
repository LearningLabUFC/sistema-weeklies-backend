"""
Dependências reutilizáveis — Autenticação.

Fornece o dependency `get_current_user` que extrai e valida
o token JWT do header Authorization e retorna o usuário
correspondente do banco de dados.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.security import decodificar_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency do FastAPI que:
    1. Extrai o Bearer token do header Authorization.
    2. Decodifica e valida o JWT.
    3. Busca o usuário no banco pelo 'sub' (ID) do payload.
    4. Levanta 401 se qualquer etapa falhar.
    """
    credenciais_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de acesso ausente ou inválido.",
        headers={"WWW-Authenticate": "Bearer"},
    )

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
    if usuario is None:
        raise credenciais_exception

    return usuario
