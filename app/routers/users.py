"""
Router — Perfil do Usuário

Endpoints: obter perfil, atualizar perfil.
Dados reais obtidos do banco de dados via token JWT.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.utils.security import hash_senha
from app.schemas import (
    ErroPadrao,
    UpdateProfileRequest,
    UsuarioCompleto,
    UsuarioPerfilResponse,
)

router = APIRouter(
    prefix="/users",
    tags=["Perfil do Usuário"],
)


def _build_usuario_completo(usuario: User) -> UsuarioCompleto:
    """Converte o modelo ORM User para o schema Pydantic UsuarioCompleto."""
    return UsuarioCompleto(
        id=usuario.id,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        matricula=usuario.matricula,
        data_nascimento=usuario.data_nascimento,
        data_ingresso=usuario.data_ingresso,
        meta_horas_semanais=usuario.meta_horas_semanais,
        foto_perfil=usuario.foto_perfil,
        curso_id=usuario.curso_id,
        status_id=usuario.status_id or UUID("00000000-0000-0000-0000-000000000000"),
        global_role=usuario.global_role or UUID("00000000-0000-0000-0000-000000000000"),
    )


# ── GET /users/me ────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UsuarioPerfilResponse,
    status_code=200,
    summary="Obter perfil do usuário logado",
    description=(
        "Retorna os dados completos do perfil do usuário autenticado. "
        "Utilizado pelo frontend para exibir a tela de perfil e preencher "
        "o estado global da aplicação."
    ),
    responses={
        401: {
            "description": "Token de acesso ausente ou inválido.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "naoAutenticado": {
                            "summary": "Não autenticado",
                            "value": {"mensagem": "Token de acesso ausente ou inválido."},
                        },
                    },
                },
            },
        },
    },
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UsuarioPerfilResponse:
    return UsuarioPerfilResponse(
        mensagem="Perfil obtido com sucesso.",
        usuario=_build_usuario_completo(current_user),
    )


# ── PUT /users/me ────────────────────────────────────────────

@router.put(
    "/me",
    response_model=UsuarioPerfilResponse,
    status_code=200,
    summary="Atualizar perfil do usuário logado",
    description=(
        "Permite que o usuário autenticado atualize seu nome completo, "
        "e-mail, foto de perfil e/ou senha. Campos não enviados "
        "permanecem inalterados."
    ),
    responses={
        401: {
            "description": "Token de acesso ausente ou inválido.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "naoAutenticado": {
                            "summary": "Não autenticado",
                            "value": {"mensagem": "Token de acesso ausente ou inválido."},
                        },
                    },
                },
            },
        },
        409: {
            "description": "Conflito — e-mail já pertence a outro usuário.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "emailDuplicado": {
                            "summary": "E-mail duplicado",
                            "value": {"mensagem": "Este e-mail já está em uso por outro usuário."},
                        },
                    },
                },
            },
        },
        422: {
            "description": "Erro de validação nos dados enviados.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "nomeVazio": {
                            "summary": "Nome vazio",
                            "value": {"mensagem": "O nome completo não pode ser uma string vazia."},
                        },
                    },
                },
            },
        },
    },
)
async def update_my_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsuarioPerfilResponse:
    # Atualizar nome completo
    if body.nome_completo is not None:
        current_user.nome_completo = body.nome_completo

    # Atualizar e-mail (verificar duplicidade)
    if body.email is not None and body.email != current_user.email:
        email_existente = db.query(User).filter(
            User.email == body.email,
            User.id != current_user.id,
        ).first()
        if email_existente:
            raise HTTPException(
                status_code=409,
                detail="Este e-mail já está em uso por outro usuário.",
            )
        current_user.email = body.email

    # Atualizar foto de perfil
    if body.foto_perfil is not None:
        current_user.foto_perfil = body.foto_perfil

    # Atualizar senha
    if body.senha is not None and body.senha != "":
        current_user.senha_hash = hash_senha(body.senha)

    db.commit()
    db.refresh(current_user)

    return UsuarioPerfilResponse(
        mensagem="Perfil atualizado com sucesso.",
        usuario=_build_usuario_completo(current_user),
    )
