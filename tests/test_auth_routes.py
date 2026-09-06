"""
Testes de Integração — Rotas de Autenticação
"""

import uuid

import pytest

from app.models.user import User

# ── Constantes e Payloads Base ───────────────────────────────

STATUS_ATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa2")
CURSO_TESTE = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa4")

VALID_REGISTER_PAYLOAD = {
    "nome_completo": "Usuário de Integração",
    "email": "integracao@teste.com",
    "senha": "SenhaForte123!",
    "matricula": "543578",
    "data_nascimento": "2000-01-01",
    "meta_horas_semanais": 12,
    "curso_id": str(CURSO_TESTE)
}

VALID_LOGIN_PAYLOAD = {
    "email": "integracao@teste.com",
    "senha": "SenhaForte123!"
}


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def usuario_ativo_logado(client, db_session):
    """Registra, ativa e loga um usuário. Retorna (user, tokens_dict)."""
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    user = db_session.query(User).filter(User.email == "integracao@teste.com").first()
    user.status_id = STATUS_ATIVO
    db_session.commit()
    res = client.post("/auth/login", json=VALID_LOGIN_PAYLOAD)
    tokens = res.json()
    return user, tokens


# ── Testes de Registro (/auth/register) ───────────────────────

def test_register_sucesso(client, db_session):
    """Deve registrar um novo usuário com sucesso e retornar 201."""
    response = client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    
    assert response.status_code == 201
    data = response.json()
    assert "token_acesso" in data
    assert data["usuario"]["email"] == "integracao@teste.com"
    
    # Verifica diretamente no banco de dados se o usuário foi criado e está pendente
    user = db_session.query(User).filter(User.email == "integracao@teste.com").first()
    assert user is not None
    assert user.status.nome == "pendente"


def test_register_email_duplicado(client):
    """Deve rejeitar o registro se o e-mail já existir no banco (409)."""
    # 1. Faz o primeiro registro com sucesso
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    
    # 2. Tenta registrar outro usuário com o mesmo e-mail, mas matrícula diferente
    payload_dup = {**VALID_REGISTER_PAYLOAD, "matricula": "666666"}
    response = client.post("/auth/register", json=payload_dup)
    
    assert response.status_code == 409
    assert "já está cadastrado" in response.json()["detail"]


def test_register_matricula_duplicada(client):
    """Deve rejeitar o registro se a matrícula já existir no banco (409)."""
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    
    payload_dup = {**VALID_REGISTER_PAYLOAD, "email": "outro@teste.com"}
    response = client.post("/auth/register", json=payload_dup)
    
    assert response.status_code == 409
    assert "já pertence a outro usuário" in response.json()["detail"]


def test_register_senha_fraca(client):
    """Deve rejeitar o registro por erro de validação (Pydantic 422) se a senha for fraca."""
    payload = {**VALID_REGISTER_PAYLOAD, "senha": "fraca"}
    response = client.post("/auth/register", json=payload)
    
    assert response.status_code == 422
    detalhes = response.json()["detail"]
    # Verifica se o erro aponta para o campo 'senha'
    assert any(erro["loc"][-1] == "senha" for erro in detalhes)


def test_register_campos_faltando(client):
    """Deve rejeitar (422) se campos obrigatórios não forem enviados."""
    payload = {"email": "novo@teste.com"}  # Faltam quase todos os campos
    response = client.post("/auth/register", json=payload)
    
    assert response.status_code == 422
    assert len(response.json()["detail"]) > 1


# ── Testes de Login (/auth/login) ─────────────────────────────

def test_login_sucesso(usuario_ativo_logado):
    """Deve autenticar com sucesso e retornar 200 + JWT."""
    _user, tokens = usuario_ativo_logado
    assert "token_acesso" in tokens
    assert tokens["usuario"]["email"] == "integracao@teste.com"


def test_login_email_inexistente(client):
    """Deve rejeitar (401) se o e-mail não existir."""
    payload = {"email": "naoexiste@teste.com", "senha": "qualquer_senha"}
    response = client.post("/auth/login", json=payload)
    
    assert response.status_code == 401
    assert "incorretos" in response.json()["detail"]


def test_login_senha_errada(client, usuario_ativo_logado):
    """Deve rejeitar (401) se a senha estiver incorreta."""
    payload = {"email": "integracao@teste.com", "senha": "SenhaErrada123!"}
    response = client.post("/auth/login", json=payload)
    
    assert response.status_code == 401
    assert "incorretos" in response.json()["detail"]


# ── Testes de Forgot Password (/auth/forgot-password) ─────────────────

def test_forgot_password_sucesso(client, db_session):
    # Registrar user primeiro
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    
    response = client.post("/auth/forgot-password", json={"email": "integracao@teste.com"})
    assert response.status_code == 200
    assert "código de 6 dígitos foi enviado" in response.json()["mensagem"]


def test_forgot_password_enumeracao(client):
    # E-mail que não existe na base
    response = client.post("/auth/forgot-password", json={"email": "fantasma@teste.com"})
    # Deve retornar 200 na mesma para evitar enumeração
    assert response.status_code == 200
    assert "código de 6 dígitos foi enviado" in response.json()["mensagem"]


def test_forgot_password_rate_limit_email(client):
    from app.config import settings
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    email = "integracao@teste.com"
    
    limite_email = settings.FORGOT_PASSWORD_MAX_REQUESTS
    for _ in range(limite_email):
        res = client.post("/auth/forgot-password", json={"email": email})
        assert res.status_code == 200
        
    # Próxima requisição deve falhar
    res = client.post("/auth/forgot-password", json={"email": email})
    assert res.status_code == 429
    assert "Limite de solicitações atingido" in res.json()["detail"]


def test_forgot_password_rate_limit_ip(client):
    from app.config import settings
    limite_ip = settings.FORGOT_PASSWORD_IP_MAX_REQUESTS
    for i in range(limite_ip):
        res = client.post("/auth/forgot-password", json={"email": f"ip_test{i}@teste.com"})
        assert res.status_code == 200
        
    res = client.post("/auth/forgot-password", json={"email": "estourou@teste.com"})
    assert res.status_code == 429
    assert "Muitas solicitações deste endereço" in res.json()["detail"]


# ── Testes de Verify Code (/auth/verify-code) ─────────────────

def test_verify_code_sucesso(client, monkeypatch):
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    
    import app.routers.auth as auth_router
    monkeypatch.setattr(auth_router, "gerar_codigo_otp", lambda: "123456")
    
    client.post("/auth/forgot-password", json={"email": "integracao@teste.com"})
    
    res = client.post("/auth/verify-code", json={"email": "integracao@teste.com", "codigo": "123456"})
    assert res.status_code == 200
    assert "token_redefinicao" in res.json()


def test_verify_code_invalido(client, monkeypatch):
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    import app.routers.auth as auth_router
    monkeypatch.setattr(auth_router, "gerar_codigo_otp", lambda: "123456")
    client.post("/auth/forgot-password", json={"email": "integracao@teste.com"})
    
    res = client.post("/auth/verify-code", json={"email": "integracao@teste.com", "codigo": "654321"})
    assert res.status_code == 401
    assert "inválido ou já expirou" in res.json()["detail"]


def test_verify_code_bruteforce(client, monkeypatch):
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    import app.routers.auth as auth_router
    monkeypatch.setattr(auth_router, "gerar_codigo_otp", lambda: "123456")
    client.post("/auth/forgot-password", json={"email": "integracao@teste.com"})
    
    # O limite de tentativas erradas é 5
    for _ in range(4):
        res = client.post("/auth/verify-code", json={"email": "integracao@teste.com", "codigo": "errado"})
        assert res.status_code == 401
        
    # A 5ª tentativa bloqueia
    res = client.post("/auth/verify-code", json={"email": "integracao@teste.com", "codigo": "errado"})
    assert res.status_code == 429
    assert "Limite de tentativas atingido" in res.json()["detail"]
    
    # A 6ª tentativa, mesmo com código CERTO, deve dar 429 porque a conta está em cooldown
    res = client.post("/auth/verify-code", json={"email": "integracao@teste.com", "codigo": "123456"})
    assert res.status_code == 429
    assert "Muitas tentativas incorretas" in res.json()["detail"]


# ── Testes de Reset Password (/auth/reset-password) ───────────

def test_reset_password_sucesso(client, monkeypatch):
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    import app.routers.auth as auth_router
    monkeypatch.setattr(auth_router, "gerar_codigo_otp", lambda: "123456")
    client.post("/auth/forgot-password", json={"email": "integracao@teste.com"})
    res_verify = client.post("/auth/verify-code", json={"email": "integracao@teste.com", "codigo": "123456"})
    token_redefinicao = res_verify.json()["token_redefinicao"]
    
    res = client.post("/auth/reset-password", json={
        "token_redefinicao": token_redefinicao,
        "nova_senha": "NovaSenhaForte123@"
    })
    assert res.status_code == 200
    assert "redefinida com sucesso" in res.json()["mensagem"]


def test_reset_password_senha_igual(client, monkeypatch):
    client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)
    import app.routers.auth as auth_router
    monkeypatch.setattr(auth_router, "gerar_codigo_otp", lambda: "123456")
    client.post("/auth/forgot-password", json={"email": "integracao@teste.com"})
    res_verify = client.post("/auth/verify-code", json={"email": "integracao@teste.com", "codigo": "123456"})
    token_redefinicao = res_verify.json()["token_redefinicao"]
    
    res = client.post("/auth/reset-password", json={
        "token_redefinicao": token_redefinicao,
        "nova_senha": "SenhaForte123!"  # Mesma de antes
    })
    assert res.status_code == 400
    assert "diferente da senha anterior" in res.json()["detail"]


def test_reset_password_token_invalido(client):
    res = client.post("/auth/reset-password", json={
        "token_redefinicao": "token_inventado_invalido",
        "nova_senha": "NovaSenhaForte123@"
    })
    assert res.status_code == 401
    assert "expirada" in res.json()["detail"]


# ── Testes de Refresh e Logout ────────────────────────────────

def test_refresh_token_sucesso(client, usuario_ativo_logado):
    _user, tokens = usuario_ativo_logado
    
    res = client.post("/auth/refresh", json={"token_atualizacao": tokens["token_atualizacao"]})
    assert res.status_code == 200
    assert "token_acesso" in res.json()
    assert res.json()["token_acesso"] != tokens["token_acesso"]
    assert res.json()["token_atualizacao"] != tokens["token_atualizacao"]


def test_refresh_token_rotacao(client, usuario_ativo_logado):
    _user, tokens = usuario_ativo_logado
    token_atualizacao = tokens["token_atualizacao"]
    
    # Usa a primeira vez - OK
    res1 = client.post("/auth/refresh", json={"token_atualizacao": token_atualizacao})
    assert res1.status_code == 200
    
    # Usa a segunda vez - DEVE FALHAR (Blacklist)
    res2 = client.post("/auth/refresh", json={"token_atualizacao": token_atualizacao})
    assert res2.status_code == 401
    assert "já foi utilizado" in res2.json()["detail"]


def test_logout_sucesso(client, usuario_ativo_logado):
    _user, tokens = usuario_ativo_logado
    token_acesso = tokens["token_acesso"]
    token_atualizacao = tokens["token_atualizacao"]
    
    # 1. Faz logout, invalidando acesso e refresh
    headers = {"Authorization": f"Bearer {token_acesso}"}
    res = client.post("/auth/logout", headers=headers, json={"token_atualizacao": token_atualizacao})
    assert res.status_code == 200
    assert "encerrada com sucesso" in res.json()["mensagem"]
    
    # 2. Tenta usar o access token novamente (deve falhar - blacklist)
    res_change_pwd = client.put("/auth/change-password", json={
        "senha_atual": "SenhaForte123!",
        "nova_senha": "NovaSenhaSegura1@"
    }, headers=headers)
    assert res_change_pwd.status_code == 401
    
    # 3. Tenta usar o refresh token novamente (deve falhar - blacklist)
    res_refresh = client.post("/auth/refresh", json={"token_atualizacao": token_atualizacao})
    assert res_refresh.status_code == 401


def test_logout_sem_token(client):
    res = client.post("/auth/logout")
    assert res.status_code == 403  # HTTPBearer retorna 403 se ausente


# ── Testes de Auth Reversa (Autenticados) ─────────────────────

def test_change_password_sucesso(client, usuario_ativo_logado):
    _user, tokens = usuario_ativo_logado
    
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}
    res = client.put("/auth/change-password", json={
        "senha_atual": "SenhaForte123!",
        "nova_senha": "NovaSenhaSegura1@"
    }, headers=headers)
    
    assert res.status_code == 200
    assert "alterada com sucesso" in res.json()["mensagem"]


def test_change_password_incorreta(client, usuario_ativo_logado):
    _user, tokens = usuario_ativo_logado
    
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}
    res = client.put("/auth/change-password", json={
        "senha_atual": "SenhaErrada!!!",
        "nova_senha": "NovaSenhaSegura1@"
    }, headers=headers)
    
    assert res.status_code == 401
    assert "incorreta" in res.json()["detail"]


def test_delete_account_sucesso(client, usuario_ativo_logado, db_session):
    user, tokens = usuario_ativo_logado
    
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}
    res = client.request("DELETE", "/auth/account", json={"senha": "SenhaForte123!"}, headers=headers)
    
    assert res.status_code == 200
    assert "desativada" in res.json()["mensagem"]
    
    # Verifica no banco se foi deletado logicamente
    db_session.refresh(user)
    assert user.status.nome == "inativo"
