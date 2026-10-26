"""
Service — Lógica de negócios de Autenticação.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import BackgroundTasks
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth.repository import (
    create_user,
    find_user_by_email,
    find_user_by_id,
    find_user_by_matricula,
    update_user,
)
from app.auth.schemas import (
    AuthTokenResponse,
    ChangePasswordRequest,
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
from app.config import settings
from app.core.email import enviar_email_otp
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    RateLimitError,
    UnauthorizedError,
)
from app.core.redis import (
    adicionar_token_blacklist,
    aplicar_cooldown_bruteforce,
    incrementar_rate_limit_email,
    incrementar_rate_limit_ip,
    limpar_tentativas,
    registrar_tentativa_falha,
    salvar_otp,
    token_na_blacklist,
    verificar_bloqueio_bruteforce,
    verificar_otp,
    verificar_rate_limit_email,
    verificar_rate_limit_ip,
)
from app.core.schemas import MensagemResponse
from app.core.security import (
    criar_token_acesso,
    criar_token_atualizacao,
    criar_token_redefinicao,
    decodificar_token,
    gerar_codigo_otp,
    hash_senha,
    verificar_senha,
)
from app.models.user import User
from app.users.schemas import UsuarioCompleto

logger = logging.getLogger("uvicorn.error")


async def svc_register_user(body: RegisterRequest, db: Session) -> AuthTokenResponse:
    if find_user_by_email(db, body.email):
        raise ConflictError("Este e-mail já está cadastrado no sistema.")
    if find_user_by_matricula(db, body.matricula):
        raise ConflictError("Esta matrícula já pertence a outro usuário.")

    novo_usuario = User(
        nome_completo=body.nome_completo,
        email=body.email,
        senha_hash=hash_senha(body.senha),
        matricula=body.matricula,
        data_nascimento=body.data_nascimento,
        data_ingresso=datetime.now(tz=timezone.utc).date(),
        meta_horas_semanais=body.meta_horas_semanais,
        foto_perfil="avatar_padrao.png",
        curso_id=body.curso_id,
        status_id=UUID("1fa85f64-5717-4562-b3fc-2c963f66afa1"),
        global_role=UUID("2fa85f64-5717-4562-b3fc-2c963f66afa3"),
    )
    novo_usuario = create_user(db, novo_usuario)

    token_dados = {"sub": str(novo_usuario.id)}
    token_acesso = criar_token_acesso(token_dados)
    token_atualizacao = criar_token_atualizacao(token_dados)

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
        status_id=novo_usuario.status_id
        or UUID("00000000-0000-0000-0000-000000000000"),
        global_role=novo_usuario.global_role
        or UUID("00000000-0000-0000-0000-000000000000"),
    )

    return AuthTokenResponse(
        mensagem="Usuário registrado com sucesso. Aguardando aprovação do administrador.",
        token_acesso=token_acesso,
        tipo_token="bearer",
        token_atualizacao=token_atualizacao,
        usuario=usuario_resposta,
    )


async def svc_login_user(body: LoginRequest, db: Session) -> AuthTokenResponse:
    usuario = find_user_by_email(db, body.email)
    if not usuario or usuario.status.nome == "inativo":
        raise UnauthorizedError("E-mail ou senha incorretos, ou conta inativa.")
    if not verificar_senha(body.senha, usuario.senha_hash):
        raise UnauthorizedError("E-mail ou senha incorretos. Tente novamente.")

    token_dados = {"sub": str(usuario.id)}
    token_acesso = criar_token_acesso(token_dados)
    token_atualizacao = criar_token_atualizacao(token_dados)

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


async def svc_forgot_password(
    body: ForgotPasswordRequest,
    client_ip: str,
    background_tasks: BackgroundTasks,
    db: Session,
) -> MensagemResponse:
    mensagem_generica = (
        "Se o e-mail estiver cadastrado, um código de 6 dígitos foi enviado."
    )
    if not await verificar_rate_limit_ip(client_ip):
        raise RateLimitError(
            "Muitas solicitações deste endereço. Tente novamente mais tarde.",
        )
    if not await verificar_rate_limit_email(body.email):
        raise RateLimitError(
            "Limite de solicitações atingido para este e-mail. Tente novamente em alguns minutos.",
        )

    usuario = find_user_by_email(db, body.email)
    if not usuario:
        await incrementar_rate_limit_ip(client_ip)
        return MensagemResponse(mensagem=mensagem_generica)

    codigo = gerar_codigo_otp()
    await salvar_otp(body.email, codigo)
    await incrementar_rate_limit_email(body.email)
    await incrementar_rate_limit_ip(client_ip)

    background_tasks.add_task(enviar_email_otp, body.email, codigo)
    return MensagemResponse(mensagem=mensagem_generica)


async def svc_verify_code(body: VerifyCodeRequest, db: Session) -> VerifyCodeResponse:
    if await verificar_bloqueio_bruteforce(body.email):
        raise RateLimitError(
            f"Muitas tentativas incorretas. Solicite um novo código após {settings.VERIFY_CODE_COOLDOWN_MINUTES} minutos.",
        )

    otp_valido = await verificar_otp(body.email, body.codigo)
    if not otp_valido:
        tentativas = await registrar_tentativa_falha(body.email)
        if tentativas >= settings.VERIFY_CODE_MAX_ATTEMPTS:
            await aplicar_cooldown_bruteforce(body.email)
            raise RateLimitError(
                f"Limite de tentativas atingido. O código foi invalidado. Solicite um novo após {settings.VERIFY_CODE_COOLDOWN_MINUTES} minutos.",
            )
        raise UnauthorizedError("O código inserido é inválido ou já expirou.")

    await limpar_tentativas(body.email)

    usuario = find_user_by_email(db, body.email)
    if not usuario:
        raise UnauthorizedError("O código inserido é inválido ou já expirou.")

    token = criar_token_redefinicao(str(usuario.id))
    return VerifyCodeResponse(
        mensagem="Código validado com sucesso.", token_redefinicao=token
    )


async def svc_reset_password(
    body: ResetPasswordRequest, db: Session
) -> MensagemResponse:
    payload = decodificar_token(body.token_redefinicao)
    if payload is None or payload.get("tipo") != "redefinicao":
        raise UnauthorizedError(
            "Sessão de redefinição expirada. Solicite um novo código.",
        )
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError(
            "Sessão de redefinição expirada. Solicite um novo código.",
        )

    usuario = find_user_by_id(db, user_id)
    if not usuario:
        raise UnauthorizedError(
            "Sessão de redefinição expirada. Solicite um novo código.",
        )

    if verificar_senha(body.nova_senha, usuario.senha_hash):
        raise BadRequestError("A nova senha deve ser diferente da senha anterior.")

    usuario.senha_hash = hash_senha(body.nova_senha)
    usuario.senha_atualizada_em = datetime.now(timezone.utc)
    update_user(db, usuario)

    logger.info("🔒 Senha redefinida com sucesso para user_id=%s", user_id)
    return MensagemResponse(
        mensagem="Sua senha foi redefinida com sucesso. Você já pode realizar o login."
    )


async def svc_logout_user(
    body: LogoutRequest, auth: HTTPAuthorizationCredentials
) -> MensagemResponse:
    payload_acesso = decodificar_token(auth.credentials)
    if payload_acesso:
        jti = payload_acesso.get("jti")
        exp = payload_acesso.get("exp", 0)
        ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 0)
        if jti:
            await adicionar_token_blacklist(jti, ttl)

    if body.token_atualizacao:
        payload_refresh = decodificar_token(body.token_atualizacao)
        if payload_refresh:
            jti = payload_refresh.get("jti")
            exp = payload_refresh.get("exp", 0)
            ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 0)
            if jti:
                await adicionar_token_blacklist(jti, ttl)

    return MensagemResponse(mensagem="Sessão encerrada com sucesso.")


async def svc_refresh_token(
    body: RefreshTokenRequest, db: Session
) -> RefreshTokenResponse:
    payload = decodificar_token(body.token_atualizacao)
    if payload is None or payload.get("tipo") != "atualizacao":
        raise UnauthorizedError("Refresh token inválido ou expirado.")

    jti = payload.get("jti")
    if jti and await token_na_blacklist(jti):
        raise UnauthorizedError("Refresh token já foi utilizado.")

    user_id = payload.get("sub")
    usuario = find_user_by_id(db, user_id)
    if not usuario or usuario.status.nome != "ativo":
        raise UnauthorizedError("Refresh token inválido ou expirado.")

    if jti:
        exp = payload.get("exp", 0)
        ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 0)
        await adicionar_token_blacklist(jti, ttl)

    token_dados = {"sub": str(usuario.id)}
    novo_acesso = criar_token_acesso(token_dados)
    novo_atualizacao = criar_token_atualizacao(token_dados)

    return RefreshTokenResponse(
        mensagem="Token renovado com sucesso.",
        token_acesso=novo_acesso,
        tipo_token="bearer",
        token_atualizacao=novo_atualizacao,
    )


async def svc_change_password(
    body: ChangePasswordRequest, current_user: User, db: Session
) -> MensagemResponse:
    if not verificar_senha(body.senha_atual, current_user.senha_hash):
        raise UnauthorizedError("A senha atual informada está incorreta.")

    if verificar_senha(body.nova_senha, current_user.senha_hash):
        raise BadRequestError("A nova senha deve ser diferente da senha atual.")

    current_user.senha_hash = hash_senha(body.nova_senha)
    current_user.senha_atualizada_em = datetime.now(timezone.utc)
    update_user(db, current_user)

    return MensagemResponse(mensagem="Senha alterada com sucesso.")
