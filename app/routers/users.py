"""
Router — Perfil do Usuário

Endpoints: obter perfil, atualizar perfil.
Dados mockados para visualização no Swagger.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter

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

# ── Dados mockados reutilizáveis ─────────────────────────────

_MOCK_USUARIO = UsuarioCompleto(
    nome_completo="João Silva",
    email="joao@exemplo.com",
    matricula="512345",
    data_nascimento=date(2000, 1, 1),
    data_ingresso=date(2024, 5, 20),
    meta_horas_semanais=12,
    foto_perfil="avatar_padrao.png",
    curso_id=UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
    status_id=UUID("1fa85f64-5717-4562-b3fc-2c963f66afa1"),
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
async def get_my_profile() -> UsuarioPerfilResponse:
    return UsuarioPerfilResponse(
        mensagem="Perfil obtido com sucesso.",
        usuario=_MOCK_USUARIO,
    )


# ── PUT /users/me ────────────────────────────────────────────

@router.put(
    "/me",
    response_model=UsuarioPerfilResponse,
    status_code=200,
    summary="Atualizar perfil do usuário logado",
    description=(
        "Permite que o usuário autenticado atualize seu nome completo "
        "e/ou foto de perfil. Campos não enviados permanecem inalterados."
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
async def update_my_profile(body: UpdateProfileRequest) -> UsuarioPerfilResponse:
    # Em produção, aplicaria as alterações no banco de dados.
    # No mock, retorna o usuário com o nome atualizado se fornecido.
    usuario_atualizado = _MOCK_USUARIO.model_copy(
        update={
            k: v
            for k, v in body.model_dump().items()
            if v is not None
        }
    )
    return UsuarioPerfilResponse(
        mensagem="Perfil atualizado com sucesso.",
        usuario=usuario_atualizado,
    )
