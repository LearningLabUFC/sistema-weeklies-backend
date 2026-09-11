from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.helpers import build_usuario_completo
from app.models.user import User
from app.users.schemas import UpdateProfileRequest, UsuarioPerfilResponse


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
        email_existente = (
            db.query(User)
            .filter(
                User.email == body.email,
                User.id != current_user.id,
            )
            .first()
        )
        if email_existente:
            raise HTTPException(
                status_code=409,
                detail="Este e-mail já está em uso por outro usuário.",
            )
        current_user.email = body.email

    if body.foto_perfil is not None:
        current_user.foto_perfil = body.foto_perfil

    db.commit()
    db.refresh(current_user)

    return UsuarioPerfilResponse(
        mensagem="Perfil atualizado com sucesso.",
        usuario=build_usuario_completo(current_user),
    )
