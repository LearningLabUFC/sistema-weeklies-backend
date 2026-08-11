"""
Router — Autenticação e Identidade

Endpoints: register, login, forgot-password, verify-code, reset-password.
"""

import logging
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.deps import get_current_user
from app.redis import (
    salvar_otp,
    verificar_otp,
    verificar_rate_limit_email,
    incrementar_rate_limit_email,
    verificar_rate_limit_ip,
    incrementar_rate_limit_ip,
    verificar_bloqueio_bruteforce,
    registrar_tentativa_falha,
    aplicar_cooldown_bruteforce,
    limpar_tentativas,
)
from app.config import settings
from app.utils.email_service import enviar_email_otp
from app.utils.security import (
    hash_senha,
    verificar_senha,
    criar_token_acesso,
    criar_token_atualizacao,
    criar_token_redefinicao,
    decodificar_token,
    gerar_codigo_otp,
)

logger = logging.getLogger("uvicorn.error")

from app.schemas import (
    AuthTokenResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ErroPadrao,
    ForgotPasswordRequest,
    LoginRequest,
    MensagemResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
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
async def register_user(body: RegisterRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    # Verificar se e-mail já existe
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado no sistema.")

    # Verificar se matrícula já existe
    if db.query(User).filter(User.matricula == body.matricula).first():
        raise HTTPException(status_code=409, detail="Esta matrícula já pertence a outro usuário.")

    # Criar o usuário no banco de dados
    novo_usuario = User(
        nome_completo=body.nome_completo,
        email=body.email,
        senha_hash=hash_senha(body.senha),
        matricula=body.matricula,
        data_nascimento=body.data_nascimento,
        data_ingresso=date.today(),
        meta_horas_semanais=body.metas_horas_semanais,
        foto_perfil="avatar_padrao.png",
        curso_id=body.curso_id,
        status_id=UUID("1fa85f64-5717-4562-b3fc-2c963f66afa1"),  # Pendente
        global_role=UUID("2fa85f64-5717-4562-b3fc-2c963f66afa3"),  # Aluno
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)

    # Gerar tokens JWT reais
    token_dados = {"sub": str(novo_usuario.id)}
    token_acesso = criar_token_acesso(token_dados)
    token_atualizacao = criar_token_atualizacao(token_dados)

    # Montar resposta com os dados do usuário criado
    usuario_resposta = UsuarioCompleto(
        id=novo_usuario.id,
        nome_completo=novo_usuario.nome_completo,
        email=novo_usuario.email,
        matricula=novo_usuario.matricula,
        data_nascimento=novo_usuario.data_nascimento,
        data_ingresso=novo_usuario.data_ingresso,
        meta_horas_semanais=novo_usuario.meta_horas_semanais,
        foto_perfil=novo_usuario.foto_perfil,
        curso_id=novo_usuario.curso_id,
        status_id=novo_usuario.status_id or UUID("00000000-0000-0000-0000-000000000000"),
        global_role=novo_usuario.global_role or UUID("00000000-0000-0000-0000-000000000000"),
    )

    return AuthTokenResponse(
        mensagem="Usuário registrado com sucesso. Aguardando aprovação do administrador.",
        token_acesso=token_acesso,
        tipo_token="bearer",
        token_atualizacao=token_atualizacao,
        usuario=usuario_resposta,
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
async def login_user(body: LoginRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    # Buscar usuário pelo e-mail
    usuario = db.query(User).filter(User.email == body.email).first()

    if not usuario or usuario.status.nome == 'inativo':
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos, ou conta inativa.")

    # Verificar senha contra o hash armazenado
    if not verificar_senha(body.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos. Tente novamente.")

    # Gerar tokens JWT reais
    token_dados = {"sub": str(usuario.id)}
    token_acesso = criar_token_acesso(token_dados)
    token_atualizacao = criar_token_atualizacao(token_dados)

    # Montar resposta com os dados do usuário
    usuario_resposta = UsuarioCompleto(
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

    return AuthTokenResponse(
        mensagem="Login realizado com sucesso.",
        token_acesso=token_acesso,
        tipo_token="bearer",
        token_atualizacao=token_atualizacao,
        usuario=usuario_resposta,
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
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MensagemResponse:
    # Mensagem genérica — nunca revelar se o e-mail existe ou não
    mensagem_generica = "Se o e-mail estiver cadastrado, um código de 6 dígitos foi enviado."

    # Rate limit por IP (global)
    client_ip = request.client.host if request.client else "unknown"
    if not await verificar_rate_limit_ip(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Muitas solicitações deste endereço. Tente novamente mais tarde.",
        )

    # Rate limit por e-mail
    if not await verificar_rate_limit_email(body.email):
        raise HTTPException(
            status_code=429,
            detail="Limite de solicitações atingido para este e-mail. Tente novamente em alguns minutos.",
        )

    usuario = db.query(User).filter(User.email == body.email).first()
    if not usuario:
        # Incrementar rate limit de IP mesmo sem usuário (evitar enumeração)
        await incrementar_rate_limit_ip(client_ip)
        # Retorna a mesma mensagem para não vazar informação
        return MensagemResponse(mensagem=mensagem_generica)

    # Gerar código OTP e salvar no Redis com TTL de 15 min
    codigo = gerar_codigo_otp()
    await salvar_otp(body.email, codigo)

    # Incrementar rate limits
    await incrementar_rate_limit_email(body.email)
    await incrementar_rate_limit_ip(client_ip)

    # Enviar e-mail em background (não bloqueia a resposta)
    background_tasks.add_task(enviar_email_otp, body.email, codigo)

    return MensagemResponse(mensagem=mensagem_generica)


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
async def verify_code(
    body: VerifyCodeRequest,
    db: Session = Depends(get_db),
) -> VerifyCodeResponse:
    # Verificar se o e-mail está em cooldown (brute-force)
    if await verificar_bloqueio_bruteforce(body.email):
        raise HTTPException(
            status_code=429,
            detail=(
                "Muitas tentativas incorretas. Solicite um novo código "
                f"após {settings.VERIFY_CODE_COOLDOWN_MINUTES} minutos."
            ),
        )

    # Verificar o código OTP no Redis
    otp_valido = await verificar_otp(body.email, body.codigo)
    if not otp_valido:
        # Registrar tentativa falha
        tentativas = await registrar_tentativa_falha(body.email)
        if tentativas >= settings.VERIFY_CODE_MAX_ATTEMPTS:
            await aplicar_cooldown_bruteforce(body.email)
            raise HTTPException(
                status_code=429,
                detail=(
                    "Limite de tentativas atingido. O código foi invalidado. "
                    f"Solicite um novo após {settings.VERIFY_CODE_COOLDOWN_MINUTES} minutos."
                ),
            )
        raise HTTPException(
            status_code=401,
            detail="O código inserido é inválido ou já expirou.",
        )

    # Código correto — limpar tentativas
    await limpar_tentativas(body.email)

    # Buscar usuário para gerar o token de redefinição
    usuario = db.query(User).filter(User.email == body.email).first()
    if not usuario:
        raise HTTPException(
            status_code=401,
            detail="O código inserido é inválido ou já expirou.",
        )

    # Gerar JWT de redefinição (5 min de validade)
    token = criar_token_redefinicao(str(usuario.id))

    return VerifyCodeResponse(
        mensagem="Código validado com sucesso.",
        token_redefinicao=token,
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
async def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MensagemResponse:
    # Validar o token de redefinição
    payload = decodificar_token(body.token_redefinicao)
    if payload is None or payload.get("tipo") != "redefinicao":
        raise HTTPException(
            status_code=401,
            detail="Sessão de redefinição expirada. Solicite um novo código.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Sessão de redefinição expirada. Solicite um novo código.",
        )

    # Buscar usuário e atualizar senha
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(
            status_code=401,
            detail="Sessão de redefinição expirada. Solicite um novo código.",
        )

    # Verificar se a nova senha é igual à atual
    if verificar_senha(body.nova_senha, usuario.senha_hash):
        raise HTTPException(
            status_code=400,
            detail="A nova senha deve ser diferente da senha anterior.",
        )

    usuario.senha_hash = hash_senha(body.nova_senha)
    usuario.senha_atualizada_em = datetime.now(timezone.utc)
    db.commit()

    logger.info("🔒 Senha redefinida com sucesso para user_id=%s", user_id)

    return MensagemResponse(
        mensagem="Sua senha foi redefinida com sucesso. Você já pode realizar o login.",
    )


# ── POST /auth/logout ───────────────────────────────────────

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
                            "value": {"mensagem": "Token de acesso ausente ou inválido."},
                        },
                    },
                },
            },
        },
    },
)
async def logout_user() -> MensagemResponse:
    return MensagemResponse(
        mensagem="Sessão encerrada com sucesso.",
    )


# ── POST /auth/refresh ──────────────────────────────────────

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
                            "value": {"mensagem": "O refresh token expirou. Faça login novamente."},
                        },
                        "tokenInvalido": {
                            "summary": "Token inválido",
                            "value": {"mensagem": "Refresh token inválido ou já utilizado."},
                        },
                    },
                },
            },
        },
    },
)
async def refresh_token(body: RefreshTokenRequest) -> RefreshTokenResponse:
    return RefreshTokenResponse(
        mensagem="Token renovado com sucesso.",
        token_acesso="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...novoToken",
        tipo_token="bearer",
        token_atualizacao="ghi78900novoRefreshToken...",
    )


# ── PUT /auth/change-password ───────────────────────────────

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
                            "value": {"mensagem": "A nova senha deve conter no mínimo 8 caracteres, incluindo números e símbolos."},
                        },
                        "senhaIgual": {
                            "summary": "Senha igual à anterior",
                            "value": {"mensagem": "A nova senha deve ser diferente da senha atual."},
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
                            "value": {"mensagem": "A senha atual informada está incorreta."},
                        },
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
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MensagemResponse:
    # Validar senha atual
    if not verificar_senha(body.senha_atual, current_user.senha_hash):
        raise HTTPException(
            status_code=401,
            detail="A senha atual informada está incorreta.",
        )

    # Verificar se a nova senha é igual à atual
    if verificar_senha(body.nova_senha, current_user.senha_hash):
        raise HTTPException(
            status_code=400,
            detail="A nova senha deve ser diferente da senha atual.",
        )

    # Atualizar com o novo hash e invalidar sessões antigas
    current_user.senha_hash = hash_senha(body.nova_senha)
    current_user.senha_atualizada_em = datetime.now(timezone.utc)
    db.commit()

    return MensagemResponse(
        mensagem="Senha alterada com sucesso.",
    )


# ── DELETE /auth/account ────────────────────────────────────

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
                            "value": {"mensagem": "A senha informada está incorreta. A conta não foi excluída."},
                        },
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
async def delete_account(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MensagemResponse:
    # Validar senha de confirmação
    if not verificar_senha(body.senha, current_user.senha_hash):
        raise HTTPException(
            status_code=401,
            detail="A senha informada está incorreta. A conta não foi excluída.",
        )

    # Soft delete — mudar status para inativo
    current_user.status_id = UUID("1fa85f64-5717-4562-b3fc-2c963f66afa3")  # Inativo
    db.commit()

    return MensagemResponse(
        mensagem="Sua conta foi desativada com sucesso.",
    )

