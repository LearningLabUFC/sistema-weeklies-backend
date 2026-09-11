"""Validadores reutilizáveis (regex e funções)."""

import re

_SENHA_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)"
    r"(?=.*[!@#$%^&*()_+\-=\[\]{}|;:'\",.<>?/`~])"
    r".{8,}$"
)

_SENHA_MSG = (
    "A senha deve conter no mínimo 8 caracteres, incluindo "
    "letra maiúscula, letra minúscula, número e caractere especial."
)

_MATRICULA_REGEX = re.compile(r"^\d{6}$")
_MATRICULA_MSG = "A matrícula deve conter exatamente 6 dígitos numéricos."

_NOME_REGEX = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s'-]+$")
_NOME_MSG = "O nome completo deve conter apenas letras, acentos e espaços, e possuir ao menos nome e sobrenome."


def _validar_nome_completo(v: str) -> str:
    v = v.strip()
    if not v or not _NOME_REGEX.match(v) or len(v.split()) < 2:
        raise ValueError(_NOME_MSG)
    return v
