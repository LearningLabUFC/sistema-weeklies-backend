"""
Testes de Integração — Rotas de Perfil do Usuário (/users)
"""

import uuid

import pytest

from app.models.user import User

# ── Constantes ───────────────────────────────────────────────

STATUS_ATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa2")
CURSO_TESTE = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa4")

VALID_REGISTER_PAYLOAD = {
    "nome_completo": "Usuário de Integração",
    "email": "integracao@teste.com",
    "senha": "SenhaForte123!",
    "matricula": "543578",
    "data_nascimento": "2000-01-01",
    "meta_horas_semanais": 12,
    "curso_id": str(CURSO_TESTE),
}

VALID_LOGIN_PAYLOAD = {
    "email": "integracao@teste.com",
    "senha": "SenhaForte123!",
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


# ── Testes de GET /users/me ──────────────────────────────────

def test_get_me_sucesso(client, usuario_ativo_logado):
    """Deve retornar o perfil completo do usuário autenticado."""
    _user, tokens = usuario_ativo_logado
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}

    res = client.get("/users/me", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["mensagem"] == "Perfil obtido com sucesso."
    assert data["usuario"]["email"] == "integracao@teste.com"
    assert data["usuario"]["nome_completo"] == "Usuário de Integração"
    assert data["usuario"]["matricula"] == "543578"
    assert data["usuario"]["curso_id"] == str(CURSO_TESTE)
    assert data["usuario"]["status_id"] == str(STATUS_ATIVO)


def test_get_me_sem_token(client):
    """Deve rejeitar (403) chamadas sem token JWT."""
    res = client.get("/users/me")
    assert res.status_code == 403


def test_get_me_token_invalido(client):
    """Deve rejeitar (401) chamadas com token JWT inválido."""
    headers = {"Authorization": "Bearer token_inventado_invalido"}
    res = client.get("/users/me", headers=headers)
    assert res.status_code == 401


# ── Testes de PUT /users/me ──────────────────────────────────

def test_update_me_nome(client, usuario_ativo_logado):
    """Deve atualizar apenas o nome e retornar os dados atualizados."""
    _user, tokens = usuario_ativo_logado
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}

    res = client.put("/users/me", json={
        "nome_completo": "Nome Atualizado"
    }, headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["mensagem"] == "Perfil atualizado com sucesso."
    assert data["usuario"]["nome_completo"] == "Nome Atualizado"
    # Email não deve ter mudado
    assert data["usuario"]["email"] == "integracao@teste.com"


def test_update_me_email(client, usuario_ativo_logado):
    """Deve permitir trocar o email para um que não esteja em uso."""
    _user, tokens = usuario_ativo_logado
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}

    res = client.put("/users/me", json={
        "email": "novoemail@teste.com"
    }, headers=headers)

    assert res.status_code == 200
    assert res.json()["usuario"]["email"] == "novoemail@teste.com"


def test_update_me_email_duplicado(client, db_session, usuario_ativo_logado):
    """Deve barrar (409) a troca para email que já pertence a outro usuário."""
    _user, tokens = usuario_ativo_logado
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}

    # Registrar um segundo usuário para gerar conflito
    segundo_payload = VALID_REGISTER_PAYLOAD.copy()
    segundo_payload["email"] = "segundo@teste.com"
    segundo_payload["matricula"] = "999999"
    client.post("/auth/register", json=segundo_payload)

    # Tentar trocar nosso email pelo email do segundo usuário
    res = client.put("/users/me", json={
        "email": "segundo@teste.com"
    }, headers=headers)

    assert res.status_code == 409
    assert "já está em uso" in res.json()["detail"]


def test_update_me_foto_perfil(client, usuario_ativo_logado):
    """Deve atualizar a foto de perfil."""
    _user, tokens = usuario_ativo_logado
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}

    res = client.put("/users/me", json={
        "foto_perfil": "novo_avatar.png"
    }, headers=headers)

    assert res.status_code == 200
    assert res.json()["usuario"]["foto_perfil"] == "novo_avatar.png"


def test_update_me_nome_invalido(client, usuario_ativo_logado):
    """Deve rejeitar (422) nome com apenas um nome (sem sobrenome)."""
    _user, tokens = usuario_ativo_logado
    headers = {"Authorization": f"Bearer {tokens['token_acesso']}"}

    res = client.put("/users/me", json={
        "nome_completo": "João"
    }, headers=headers)

    assert res.status_code == 422
