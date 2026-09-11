from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.user import User
from app.users.repository import find_user_by_email_excluding, update_user
from app.users.schemas import (
    UpdateProfileRequest,
    UsuarioPerfilResponse,
    build_usuario_completo,
)


def svc_get_my_profile(current_user: User) -> UsuarioPerfilResponse:
    return UsuarioPerfilResponse(
        mensagem="Perfil obtido com sucesso.",
        usuario=build_usuario_completo(current_user),
    )


def svc_update_my_profile(
    body: UpdateProfileRequest, current_user: User, db: Session
) -> UsuarioPerfilResponse:
    if body.nome_completo is not None:
        current_user.nome_completo = body.nome_completo

    if body.email is not None and body.email != current_user.email:
        if find_user_by_email_excluding(db, body.email, current_user.id):
            raise ConflictError(
                "Este e-mail já está em uso por outro usuário.",
            )
        current_user.email = body.email

    if body.foto_perfil is not None:
        current_user.foto_perfil = body.foto_perfil

    current_user = update_user(db, current_user)

    return UsuarioPerfilResponse(
        mensagem="Perfil atualizado com sucesso.",
        usuario=build_usuario_completo(current_user),
    )
