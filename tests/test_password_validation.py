"""
Testes unitários para validação de formato de senha.

A mesma regex (_SENHA_REGEX) é usada em 3 schemas:
- RegisterRequest (campo "senha")
- ResetPasswordRequest (campo "nova_senha")
- ChangePasswordRequest (campo "nova_senha")

Requisitos da senha:
- Mínimo 8 caracteres
- Pelo menos 1 letra maiúscula
- Pelo menos 1 letra minúscula
- Pelo menos 1 dígito
- Pelo menos 1 caractere especial
"""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    _SENHA_MSG,
    ChangePasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
)

# Campos válidos base para o RegisterRequest (evita repetição)

_REGISTER_BASE = {
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "data_nascimento": date(2000, 1, 1),
    "matricula": "512345",
    "curso_id": uuid4(),
    "meta_horas_semanais": 12,
}

# A mensagem de erro esperada vem direto do schema principal
# para garantir que o teste acompanhe mudanças no texto.


# ── Testes de senha válida ──────────────────────────────────

def test_senha_valida():
    """Senha que atende todos os requisitos deve ser aceita."""
    req = RegisterRequest(**_REGISTER_BASE, senha="SenhaForte123!")
    assert req.senha == "SenhaForte123!"


def test_senha_valida_exatamente_8_caracteres():
    """Senha com exatamente 8 caracteres (limite mínimo) deve ser aceita."""
    req = RegisterRequest(**_REGISTER_BASE, senha="Ab1!abcd")
    assert req.senha == "Ab1!abcd"


# ── Testes de senha inválida (cada regra isolada) ───────────

def test_senha_sem_letra_maiuscula():
    """Senha sem letra maiúscula deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**_REGISTER_BASE, senha="senhaforte123!")
    assert _SENHA_MSG in str(exc_info.value)


def test_senha_sem_letra_minuscula():
    """Senha sem letra minúscula deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**_REGISTER_BASE, senha="SENHAFORTE123!")
    assert _SENHA_MSG in str(exc_info.value)


def test_senha_sem_digito():
    """Senha sem dígito deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**_REGISTER_BASE, senha="SenhaForte!!!!")
    assert _SENHA_MSG in str(exc_info.value)


def test_senha_sem_caractere_especial():
    """Senha sem caractere especial deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**_REGISTER_BASE, senha="SenhaForte1234")
    assert _SENHA_MSG in str(exc_info.value)


def test_senha_com_7_caracteres():
    """Senha com 7 caracteres (abaixo do mínimo) deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**_REGISTER_BASE, senha="Ab1!abc")
    assert _SENHA_MSG in str(exc_info.value)


def test_senha_vazia():
    """Senha vazia deve ser rejeitada."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(**_REGISTER_BASE, senha="")
    assert _SENHA_MSG in str(exc_info.value)


# ── Testes nos outros schemas (mesma validação) ─────────────

def test_reset_password_senha_valida():
    """Senha forte deve ser aceita na redefinição de senha."""
    req = ResetPasswordRequest(
        token_redefinicao="token-qualquer",
        nova_senha="SenhaForte123!",
    )
    assert req.nova_senha == "SenhaForte123!"


def test_reset_password_senha_invalida():
    """Senha fraca deve ser rejeitada na redefinição de senha."""
    with pytest.raises(ValidationError) as exc_info:
        ResetPasswordRequest(
            token_redefinicao="token-qualquer",
            nova_senha="senhafraca",
        )
    assert _SENHA_MSG in str(exc_info.value)


def test_change_password_senha_valida():
    """Senha forte deve ser aceita na troca de senha."""
    req = ChangePasswordRequest(
        senha_atual="QualquerSenha123!",
        nova_senha="NovaSenha456!",
    )
    assert req.nova_senha == "NovaSenha456!"


def test_change_password_senha_invalida():
    """Senha fraca deve ser rejeitada na troca de senha."""
    with pytest.raises(ValidationError) as exc_info:
        ChangePasswordRequest(
            senha_atual="QualquerSenha123!",
            nova_senha="senhafraca",
        )
    assert _SENHA_MSG in str(exc_info.value)


def test_change_password_senha_vazia():
    """Senha vazia deve ser rejeitada na troca de senha."""
    with pytest.raises(ValidationError) as exc_info:
        ChangePasswordRequest(
            senha_atual="QualquerSenha123!",
            nova_senha="",
        )
    assert _SENHA_MSG in str(exc_info.value)
