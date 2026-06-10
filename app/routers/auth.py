"""
Router — Autenticação e Identidade

Endpoints: register, login, forgot-password, verify-code, reset-password.
Dados mockados para visualização no Swagger.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter

from app.schemas import (
    AuthTokenResponse,
    ErroPadrao,
    ForgotPasswordRequest,
    LoginRequest,
    MensagemResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UsuarioCompleto,
    VerifyCodeRequest,
    VerifyCodeResponse,
)

router = APIRouter(
    prefix="/auth",
    tags=["Autenticação e Identidade"],
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


# ── POST /auth/register ─────────────────────────────────────

@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=201,
    summary="Cadastrar novo usuário",
    description=(
        "Registra um novo aluno ou membro no sistema. Valida os dados de "
        "entrada e garante que o e-mail e a matrícula sejam únicos. Retorna "
        "os dados completos do usuário recém-criado e os tokens de acesso."
    ),
    responses={
        400: {
            "description": "Erro de validação dos dados enviados (Bad Request).",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "senhaFraca": {
                            "summary": "Senha fraca",
                            "value": {"mensagem": "A senha deve conter no mínimo 8 caracteres, incluindo números e símbolos."},
                        },
                        "formatoInvalido": {
                            "summary": "Formato inválido",
                            "value": {"mensagem": "O formato do e-mail é inválido."},
                        },
                    },
                },
            },
        },
        409: {
            "description": "Conflito de dados (E-mail ou matrícula já existentes).",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "emailExistente": {
                            "summary": "E-mail duplicado",
                            "value": {"mensagem": "Este e-mail já está cadastrado no sistema."},
                        },
                        "matriculaExistente": {
                            "summary": "Matrícula duplicada",
                            "value": {"mensagem": "Esta matrícula já pertence a outro usuário."},
                        },
                    },
                },
            },
        },
    },
)
async def register_user(body: RegisterRequest) -> AuthTokenResponse:
    return AuthTokenResponse(
        mensagem="Usuário registrado com sucesso.",
        token_acesso="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...signature",
        tipo_token="bearer",
        token_atualizacao="def50200543e332...",
        usuario=_MOCK_USUARIO,
    )


# ── POST /auth/login ────────────────────────────────────────

@router.post(
    "/login",
    response_model=AuthTokenResponse,
    status_code=200,
    summary="Autenticar usuário",
    description=(
        "Valida as credenciais do usuário e retorna o Token de Acesso (JWT), "
        "o Refresh Token e os dados completos de perfil para o frontend "
        "armazenar no estado global."
    ),
    responses={
        400: {
            "description": "Dados ausentes no corpo da requisição.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "camposFaltando": {
                            "summary": "Campos obrigatórios ausentes",
                            "value": {"mensagem": "Os campos de e-mail e senha são obrigatórios."},
                        },
                    },
                },
            },
        },
        401: {
            "description": "Credenciais inválidas (E-mail ou senha incorretos).",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "credencialInvalida": {
                            "summary": "Login incorreto",
                            "value": {"mensagem": "E-mail ou senha incorretos. Tente novamente."},
                        },
                    },
                },
            },
        },
    },
)
async def login_user(body: LoginRequest) -> AuthTokenResponse:
    return AuthTokenResponse(
        mensagem="Login realizado com sucesso.",
        token_acesso="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...signature",
        tipo_token="bearer",
        token_atualizacao="def50200543e332...",
        usuario=_MOCK_USUARIO,
    )


# ── POST /auth/forgot-password ──────────────────────────────

@router.post(
    "/forgot-password",
    response_model=MensagemResponse,
    status_code=200,
    summary="Solicitar recuperação de senha",
    description=(
        "Gera um código numérico de 6 dígitos e envia para o e-mail do "
        "usuário para iniciar o processo de recuperação de conta."
    ),
    responses={
        400: {
            "description": "Formato de e-mail inválido.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "emailInvalido": {
                            "summary": "E-mail inválido",
                            "value": {"mensagem": "O endereço de e-mail fornecido não é válido."},
                        },
                    },
                },
            },
        },
    },
)
async def forgot_password(body: ForgotPasswordRequest) -> MensagemResponse:
    return MensagemResponse(
        mensagem="Se o e-mail estiver cadastrado, um código de 6 dígitos foi enviado.",
    )


# ── POST /auth/verify-code ──────────────────────────────────

@router.post(
    "/verify-code",
    response_model=VerifyCodeResponse,
    status_code=200,
    summary="Validar código numérico (OTP)",
    description=(
        "Verifica se o código de 6 dígitos digitado pelo usuário é válido. "
        "Retorna um token temporário de redefinição em caso de sucesso."
    ),
    responses={
        401: {
            "description": "Código numérico inválido ou expirado.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "codigoInvalido": {
                            "summary": "Código expirado/inválido",
                            "value": {"mensagem": "O código inserido é inválido ou já expirou."},
                        },
                    },
                },
            },
        },
    },
)
async def verify_code(body: VerifyCodeRequest) -> VerifyCodeResponse:
    return VerifyCodeResponse(
        mensagem="Código validado com sucesso.",
        token_redefinicao="abc123xyz890tokenTemporario",
    )


# ── POST /auth/reset-password ───────────────────────────────

@router.post(
    "/reset-password",
    response_model=MensagemResponse,
    status_code=200,
    summary="Salvar nova senha",
    description=(
        "Consome o token de redefinição gerado na etapa anterior e altera "
        "a senha do usuário no banco de dados."
    ),
    responses={
        400: {
            "description": "A nova senha não atende aos requisitos mínimos de segurança.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "senhaFraca": {
                            "summary": "Senha fraca",
                            "value": {"mensagem": "A nova senha deve ser diferente da anterior e conter ao menos 8 caracteres."},
                        },
                    },
                },
            },
        },
        401: {
            "description": "O token de redefinição é inválido ou já foi utilizado.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "tokenExpirado": {
                            "summary": "Token expirado",
                            "value": {"mensagem": "Sessão de redefinição expirada. Solicite um novo código."},
                        },
                    },
                },
            },
        },
    },
)
async def reset_password(body: ResetPasswordRequest) -> MensagemResponse:
    return MensagemResponse(
        mensagem="Sua senha foi redefinida com sucesso. Você já pode realizar o login.",
    )
