"""
Utilitários de segurança — Hashing de senhas e tokens JWT.

Utiliza o algoritmo bcrypt diretamente para gerar e verificar
hashes de senha de forma segura, e python-jose para criar e
decodificar tokens JWT.
"""

import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings


# ── Hashing de senhas ────────────────────────────────────────

def hash_senha(senha: str) -> str:
    """Gera o hash bcrypt de uma senha em texto plano."""
    senha_bytes = senha.encode("utf-8")
    salt = bcrypt.gensalt()
    hash_bytes = bcrypt.hashpw(senha_bytes, salt)
    return hash_bytes.decode("utf-8")


def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    """Verifica se uma senha em texto plano corresponde ao hash armazenado."""
    return bcrypt.checkpw(
        senha_plana.encode("utf-8"),
        senha_hash.encode("utf-8"),
    )


# ── Tokens JWT ───────────────────────────────────────────────

def criar_token_acesso(dados: dict, expira_em_minutos: int | None = None) -> str:
    """Cria um access token JWT com expiração configurável."""
    payload = dados.copy()
    expiracao = datetime.now(timezone.utc) + timedelta(
        minutes=expira_em_minutos or settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    payload.update({"exp": expiracao, "iat": datetime.now(timezone.utc), "tipo": "acesso"})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def criar_token_atualizacao(dados: dict) -> str:
    """Cria um refresh token JWT com expiração de 7 dias."""
    payload = dados.copy()
    expiracao = datetime.now(timezone.utc) + timedelta(days=7)
    payload.update({"exp": expiracao, "iat": datetime.now(timezone.utc), "tipo": "atualizacao"})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def criar_token_redefinicao(user_id: str) -> str:
    """
    Cria um JWT de uso único para redefinição de senha.

    Tem expiração curta (5 minutos) e tipo 'redefinicao'
    para que não possa ser confundido com tokens de acesso.
    """
    payload = {
        "sub": user_id,
        "tipo": "redefinicao",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decodificar_token(token: str) -> dict | None:
    """Decodifica e valida um token JWT. Retorna None se inválido ou expirado."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ── OTP ──────────────────────────────────────────────────────

def gerar_codigo_otp(tamanho: int = 6) -> str:
    """
    Gera um código numérico aleatório de N dígitos para OTP.

    Utiliza ``secrets.choice`` para garantir aleatoriedade
    criptograficamente segura.
    """
    return "".join(secrets.choice(string.digits) for _ in range(tamanho))
