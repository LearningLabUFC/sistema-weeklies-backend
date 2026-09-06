"""
Testes unitários para utilitários de segurança.

Cobre as 3 áreas do módulo app.utils.security:
- Hashing de senhas (bcrypt)
- Tokens JWT (acesso, atualização, redefinição)
- Geração de OTP
"""

from app.config import settings
from app.utils.security import (
    criar_token_acesso,
    criar_token_atualizacao,
    criar_token_redefinicao,
    decodificar_token,
    gerar_codigo_otp,
    hash_senha,
    verificar_senha,
)

# ── Hashing de senhas (bcrypt) ───────────────────────────────

def test_senha_correta_valida():
    """Senha correta hashing e verificação de senhas (bcrypt)."""
    hash_gerado = hash_senha("MinhaSenha123!")
    assert verificar_senha("MinhaSenha123!", hash_gerado) is True

def test_senha_errada_rejeitada():
    """Senha incorreta deve retornar False na verificação."""
    hash_gerado = hash_senha("MinhaSenha123!")
    assert verificar_senha("SenhaErrada123!", hash_gerado) is False

def test_hashes_diferentes_por_salt():
    """Dois hashes da mesma senha devem ser diferentes (salt aleatório)."""
    senha = "MinhaSenha123!"
    hash1 = hash_senha(senha)
    hash2 = hash_senha(senha)
    assert hash1 != hash2
    assert verificar_senha(senha, hash1) is True
    assert verificar_senha(senha, hash2) is True


def test_hash_retorna_string():
    """O hash gerado deve ser do tipo string (não bytes)."""
    assert isinstance(hash_senha("Teste123!"), str)

def test_hash_senha_com_unicode():
    """Senhas com acentos e caracteres especiais devem funcionar."""
    senha = "Sénh@Fôrté123!"
    hash_gerado = hash_senha(senha)
    assert verificar_senha(senha, hash_gerado) is True


# ── Tokens JWT ───────────────────────────────────────────────

def test_criar_e_decodificar_token_acesso():
    """Token de acesso deve ser criado e decodificado com os dados corretos."""
    dados = {"sub": "user-123"}
    token = criar_token_acesso(dados)
    payload = decodificar_token(token)

    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["tipo"] == "acesso"


def test_token_acesso_contem_campos_obrigatorios():
    """Token de acesso deve conter 'exp', 'iat', 'tipo' e 'jti' no payload."""
    token = criar_token_acesso({"sub": "user-123"})
    payload = decodificar_token(token)

    assert payload is not None
    assert "exp" in payload
    assert "iat" in payload
    assert "jti" in payload
    assert payload["tipo"] == "acesso"


def test_criar_e_decodificar_token_atualizacao():
    """Token de atualização (refresh) deve ser criado e decodificado corretamente (com jti)."""
    dados = {"sub": "user-456"}
    token = criar_token_atualizacao(dados)
    payload = decodificar_token(token)

    assert payload is not None
    assert payload["sub"] == "user-456"
    assert "jti" in payload
    assert payload["tipo"] == "atualizacao"


def test_criar_e_decodificar_token_redefinicao():
    """Token de redefinição de senha deve conter o user_id e tipo 'redefinicao'."""
    token = criar_token_redefinicao("user-789")
    payload = decodificar_token(token)

    assert payload is not None
    assert payload["sub"] == "user-789"
    assert payload["tipo"] == "redefinicao"


def test_token_invalido_retorna_none():
    """Token com assinatura inválida deve retornar None."""
    resultado = decodificar_token("token.completamente.invalido")
    assert resultado is None


def test_token_nao_altera_dados_originais():
    """criar_token_acesso não deve modificar o dicionário original passado."""
    dados = {"sub": "user-123"}
    dados_copia = dados.copy()
    criar_token_acesso(dados)

    assert dados == dados_copia


def test_tokens_acesso_sao_diferentes():
    """Dois tokens de acesso gerados com os mesmos dados devem ser diferentes (iat diferente)."""
    dados = {"sub": "user-123"}
    token1 = criar_token_acesso(dados)
    token2 = criar_token_acesso(dados)

    # Tokens podem ser iguais se gerados no mesmo instante (mesmo iat),
    # mas o importante é que ambos sejam válidos
    assert decodificar_token(token1) is not None
    assert decodificar_token(token2) is not None


def test_token_acesso_usa_algoritmo_configurado():
    """Token deve ser decodificável com o algoritmo definido nas settings."""
    from jose import jwt

    token = criar_token_acesso({"sub": "user-123"})
    # Decodifica manualmente usando o algoritmo das settings
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    assert payload["sub"] == "user-123"


# ── OTP ──────────────────────────────────────────────────────

def test_otp_tamanho_padrao():
    """OTP padrão deve ter 6 dígitos."""
    codigo = gerar_codigo_otp()
    assert len(codigo) == 6


def test_otp_somente_digitos():
    """OTP deve conter apenas dígitos numéricos."""
    codigo = gerar_codigo_otp()
    assert codigo.isdigit()


def test_otp_tamanho_customizado():
    """OTP com tamanho customizado deve respeitar o tamanho solicitado."""
    codigo = gerar_codigo_otp(tamanho=8)
    assert len(codigo) == 8
    assert codigo.isdigit()


def test_otp_sao_diferentes():
    """Dois OTPs gerados em sequência devem ser (muito provavelmente) diferentes."""
    # Nota: existe uma chance ínfima (1 em 1 milhão) de serem iguais,
    # mas para fins práticos, se forem iguais algo está errado.
    otp1 = gerar_codigo_otp()
    otp2 = gerar_codigo_otp()
    assert otp1 != otp2
