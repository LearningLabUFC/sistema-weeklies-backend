from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.schemas import ErroPadrao
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.users.schemas import UpdateProfileRequest, UsuarioPerfilResponse
from app.users.service import svc_get_my_profile, svc_update_my_profile

router = APIRouter(
    prefix="/users",
    tags=["Perfil do Usuário"],
)


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
                            "value": {
                                "mensagem": "Token de acesso ausente ou inválido."
                            },
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
    return svc_get_my_profile(current_user)


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
                            "value": {
                                "mensagem": "Token de acesso ausente ou inválido."
                            },
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
                            "value": {
                                "mensagem": "Este e-mail já está em uso por outro usuário."
                            },
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
                            "value": {
                                "mensagem": "O nome completo não pode ser uma string vazia."
                            },
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
    return svc_update_my_profile(body, current_user, db)
