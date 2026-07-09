"""
Utilitários de segurança — Hashing de senhas.

Utiliza o algoritmo bcrypt diretamente para gerar e verificar
hashes de senha de forma segura.
"""

import bcrypt


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
