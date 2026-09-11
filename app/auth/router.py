"""
Router — Autenticação e Identidade
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.schemas import (
    AuthTokenResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyCodeRequest,
    VerifyCodeResponse,
)
from app.auth.service import (
    svc_change_password,
    svc_delete_account,
    svc_forgot_password,
    svc_login_user,
    svc_logout_user,
    svc_refresh_token,
    svc_register_user,
    svc_reset_password,
    svc_verify_code,
)
from app.core.schemas import ErroPadrao, MensagemResponse
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User

router = APIRouter(
    prefix="/auth",
    tags=["Autenticação e Identidade"],
)


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
                            "value": {
                                "mensagem": "A senha deve conter no mínimo 8 caracteres, incluindo números e símbolos."
                            },
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
                            "value": {
                                "mensagem": "Este e-mail já está cadastrado no sistema."
                            },
                        },
                        "matriculaExistente": {
                            "summary": "Matrícula duplicada",
                            "value": {
                                "mensagem": "Esta matrícula já pertence a outro usuário."
                            },
                        },
                    },
                },
            },
        },
    },
)
async def register_user(
    body: RegisterRequest, db: Session = Depends(get_db)
) -> AuthTokenResponse:
    return await svc_register_user(body, db)


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
                            "value": {
                                "mensagem": "Os campos de e-mail e senha são obrigatórios."
                            },
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
                            "value": {
                                "mensagem": "E-mail ou senha incorretos. Tente novamente."
                            },
                        },
                    },
                },
            },
        },
    },
)
async def login_user(
    body: LoginRequest, db: Session = Depends(get_db)
) -> AuthTokenResponse:
    return await svc_login_user(body, db)


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
                            "value": {
                                "mensagem": "O endereço de e-mail fornecido não é válido."
                            },
                        },
                    },
                },
            },
        },
    },
)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MensagemResponse:
    client_ip = request.client.host if request.client else "unknown"
    return await svc_forgot_password(body, client_ip, background_tasks, db)


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
                            "value": {
                                "mensagem": "O código inserido é inválido ou já expirou."
                            },
                        },
                    },
                },
            },
        },
    },
)
async def verify_code(
    body: VerifyCodeRequest,
    db: Session = Depends(get_db),
) -> VerifyCodeResponse:
    return await svc_verify_code(body, db)


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
                            "value": {
                                "mensagem": "A nova senha deve ser diferente da anterior e conter ao menos 8 caracteres."
                            },
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
                            "value": {
                                "mensagem": "Sessão de redefinição expirada. Solicite um novo código."
                            },
                        },
                    },
                },
            },
        },
    },
)
async def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MensagemResponse:
    return await svc_reset_password(body, db)


@router.post(
    "/logout",
    response_model=MensagemResponse,
    status_code=200,
    summary="Encerrar sessão do usuário",
    description=(
        "Invalida o refresh token do usuário, encerrando a sessão atual. "
        "O access token continua válido até expirar, mas o frontend deve "
        "descartá-lo do estado local."
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
async def logout_user(
    body: LogoutRequest,
    current_user: User = Depends(get_current_user),
    auth: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
) -> MensagemResponse:
    return await svc_logout_user(body, auth)


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    status_code=200,
    summary="Renovar token de acesso",
    description=(
        "Recebe o refresh token atual e retorna um novo par de tokens "
        "(access + refresh). Implementa rotação de tokens para maior segurança."
    ),
    responses={
        401: {
            "description": "Refresh token inválido, expirado ou já utilizado.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "tokenExpirado": {
                            "summary": "Token expirado",
                            "value": {
                                "mensagem": "O refresh token expirou. Faça login novamente."
                            },
                        },
                        "tokenInvalido": {
                            "summary": "Token inválido",
                            "value": {
                                "mensagem": "Refresh token inválido ou já utilizado."
                            },
                        },
                    },
                },
            },
        },
    },
)
async def refresh_token(
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> RefreshTokenResponse:
    return await svc_refresh_token(body, db)


@router.put(
    "/change-password",
    response_model=MensagemResponse,
    status_code=200,
    summary="Alterar senha (autenticado)",
    description=(
        "Permite que um usuário autenticado altere sua senha atual. "
        "Exige a senha atual para confirmação e valida os requisitos "
        "mínimos de segurança da nova senha."
    ),
    responses={
        400: {
            "description": "A nova senha não atende aos requisitos mínimos.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "senhaFraca": {
                            "summary": "Senha fraca",
                            "value": {
                                "mensagem": "A nova senha deve conter no mínimo 8 caracteres, incluindo números e símbolos."
                            },
                        },
                        "senhaIgual": {
                            "summary": "Senha igual à anterior",
                            "value": {
                                "mensagem": "A nova senha deve ser diferente da senha atual."
                            },
                        },
                    },
                },
            },
        },
        401: {
            "description": "Senha atual incorreta ou token de acesso inválido.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "senhaIncorreta": {
                            "summary": "Senha atual incorreta",
                            "value": {
                                "mensagem": "A senha atual informada está incorreta."
                            },
                        },
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
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MensagemResponse:
    return await svc_change_password(body, current_user, db)


@router.delete(
    "/account",
    response_model=MensagemResponse,
    status_code=200,
    summary="Excluir conta do usuário",
    description=(
        "Remove permanentemente a conta do usuário autenticado. "
        "Exige a senha atual como confirmação para evitar exclusões "
        "acidentais. Esta ação é irreversível."
    ),
    responses={
        401: {
            "description": "Senha de confirmação incorreta ou token inválido.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "senhaIncorreta": {
                            "summary": "Senha incorreta",
                            "value": {
                                "mensagem": "A senha informada está incorreta. A conta não foi excluída."
                            },
                        },
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
async def delete_account(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MensagemResponse:
    return await svc_delete_account(body, current_user, db)
