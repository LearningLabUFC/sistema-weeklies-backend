"""
Testes de Integração — Rotas de Administração (/admin)
"""

import uuid

import pytest

from app.models.user import User

# ── Constantes (Seeds) ───────────────────────────────────────

STATUS_PENDENTE = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa1")
STATUS_ATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa2")
STATUS_INATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa3")

ROLE_SUPER_ADMIN = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa1")
ROLE_ADMIN = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa2")
ROLE_ALUNO = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa3")

CURSO_TESTE = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa4")


# ── Helpers ──────────────────────────────────────────────────

def _registrar_e_logar(client, db_session, email, matricula, role_id):
    """Registra um usuário, ativa, seta o role e faz login. Retorna (user, token)."""
    payload = {
        "nome_completo": f"Teste {email.split('@')[0].title()}",
        "email": email,
        "senha": "SenhaForte123!",
        "matricula": matricula,
        "data_nascimento": "2000-01-01",
        "meta_horas_semanais": 12,
        "curso_id": str(CURSO_TESTE),
    }
    client.post("/auth/register", json=payload)
    user = db_session.query(User).filter(User.email == email).first()
    user.status_id = STATUS_ATIVO
    user.global_role = role_id
    db_session.commit()
    res_login = client.post("/auth/login", json={"email": email, "senha": "SenhaForte123!"})
    return user, res_login.json()["token_acesso"]


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def admin_logado(client, db_session):
    """Cria e loga um usuário com role 'admin'."""
    return _registrar_e_logar(client, db_session, "admin@teste.com", "100001", ROLE_ADMIN)


@pytest.fixture
def super_admin_logado(client, db_session):
    """Cria e loga um usuário com role 'super_admin'."""
    return _registrar_e_logar(client, db_session, "super@teste.com", "100002", ROLE_SUPER_ADMIN)


@pytest.fixture
def aluno_logado(client, db_session):
    """Cria e loga um usuário com role 'aluno'."""
    return _registrar_e_logar(client, db_session, "aluno@teste.com", "100003", ROLE_ALUNO)


@pytest.fixture
def aluno_pendente(client, db_session):
    """Registra um aluno que fica com status 'pendente' (sem ativar). Retorna o user."""
    payload = {
        "nome_completo": "Aluno Pendente",
        "email": "pendente@teste.com",
        "senha": "SenhaForte123!",
        "matricula": "100004",
        "data_nascimento": "2000-01-01",
        "meta_horas_semanais": 12,
        "curso_id": str(CURSO_TESTE),
    }
    client.post("/auth/register", json=payload)
    return db_session.query(User).filter(User.email == "pendente@teste.com").first()


# ── Testes de GET /admin/users ───────────────────────────────

def test_list_users_admin(client, admin_logado):
    """Admin deve conseguir listar usuários com paginação."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/admin/users", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert "usuarios" in data
    assert "total" in data
    assert data["pagina"] == 1
    assert data["limite"] == 20


def test_list_users_aluno_bloqueado(client, aluno_logado):
    """Alunos NÃO podem acessar a lista de usuários (403)."""
    _user, token = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/admin/users", headers=headers)

    assert res.status_code == 403
    assert "permissão" in res.json()["detail"].lower() or "Acesso negado" in res.json()["detail"]


# ── Testes de GET /admin/users/pending ───────────────────────

def test_list_pending_admin(client, admin_logado, aluno_pendente):
    """Admin deve ver os usuários pendentes na lista."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/admin/users/pending", headers=headers)

    assert res.status_code == 200
    emails = [u["email"] for u in res.json()]
    assert "pendente@teste.com" in emails


def test_list_pending_aluno_bloqueado(client, aluno_logado):
    """Alunos NÃO podem acessar a lista de pendentes (403)."""
    _user, token = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/admin/users/pending", headers=headers)

    assert res.status_code == 403


# ── Testes de PATCH /admin/users/{user_id}/status ────────────

def test_change_status_aprovar_admin(client, admin_logado, aluno_pendente):
    """Admin deve conseguir aprovar (mudar para 'ativo') um aluno pendente."""
    _admin, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/admin/users/{aluno_pendente.id}/status",
        json={"novo_status": "ativo"},
        headers=headers,
    )

    assert res.status_code == 200
    assert "com sucesso" in res.json()["mensagem"]


def test_change_status_rejeitar_admin(client, admin_logado, aluno_pendente):
    """Admin deve conseguir rejeitar (mudar para 'inativo') um aluno pendente."""
    _admin, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/admin/users/{aluno_pendente.id}/status",
        json={"novo_status": "inativo"},
        headers=headers,
    )

    assert res.status_code == 200
    assert "com sucesso" in res.json()["mensagem"]


def test_change_status_aluno_bloqueado(client, aluno_logado, aluno_pendente):
    """Alunos não podem alterar status de ninguém (403)."""
    _user, token = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/admin/users/{aluno_pendente.id}/status",
        json={"novo_status": "ativo"},
        headers=headers,
    )

    assert res.status_code == 403


def test_change_status_admin_nao_altera_superadmin(client, admin_logado, super_admin_logado):
    """Um admin normal não pode alterar o status de um super_admin (403)."""
    _admin, token_admin = admin_logado
    super_admin, _token_super = super_admin_logado
    headers = {"Authorization": f"Bearer {token_admin}"}

    res = client.patch(
        f"/admin/users/{super_admin.id}/status",
        json={"novo_status": "inativo"},
        headers=headers,
    )

    assert res.status_code == 403
    assert "apenas outro super_admin pode" in res.json()["detail"].lower()


def test_change_status_invalido(client, admin_logado, aluno_pendente):
    """Deve retornar erro limpo ao tentar usar status inexistente (400)."""
    _admin, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/admin/users/{aluno_pendente.id}/status",
        json={"novo_status": "invalido"},
        headers=headers,
    )

    assert res.status_code == 400
    assert "inválido" in res.json()["detail"].lower()


# ── Testes de PATCH /admin/users/{user_id}/role ──────────────

def test_change_role_promover_aluno(client, admin_logado, aluno_logado):
    """Admin deve conseguir promover um aluno a admin."""
    _admin, token = admin_logado
    aluno, _token_aluno = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/admin/users/{aluno.id}/role",
        json={"role_nome": "admin"},
        headers=headers,
    )

    assert res.status_code == 200
    assert "com sucesso" in res.json()["mensagem"]


def test_change_role_auto_rebaixamento(client, admin_logado):
    """Admin não pode rebaixar a si mesmo (403)."""
    admin, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/admin/users/{admin.id}/role",
        json={"role_nome": "aluno"},
        headers=headers,
    )

    assert res.status_code == 403
    assert "próprio cargo" in res.json()["detail"].lower()


def test_change_role_admin_nao_rebaixa_superadmin(client, admin_logado, super_admin_logado):
    """Admin normal não pode rebaixar um super_admin (403)."""
    _admin, token_admin = admin_logado
    super_admin, _token_super = super_admin_logado
    headers = {"Authorization": f"Bearer {token_admin}"}

    res = client.patch(
        f"/admin/users/{super_admin.id}/role",
        json={"role_nome": "admin"},
        headers=headers,
    )

    assert res.status_code == 403
    assert "apenas um super_admin" in res.json()["detail"].lower()


def test_change_role_usuario_pendente(client, admin_logado, aluno_pendente):
    """Deve barrar (400) a promoção de alguém que não está com status 'ativo'."""
    _admin, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/admin/users/{aluno_pendente.id}/role",
        json={"role_nome": "admin"},
        headers=headers,
    )

    assert res.status_code == 400
    assert "status ativo" in res.json()["detail"].lower()


def test_change_role_ultimo_admin(client, super_admin_logado, db_session):
    """Deve barrar (409) a remoção do último administrador do sistema."""
    _super_admin, token = super_admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    # Como a API possui proteção contra auto-rebaixamento e a checagem
    # verifica se há <= 1 admin ativo (o que é matematicamente inalcançável 
    # sem concorrência, já que o próprio requisitante + alvo = 2), 
    # nós usamos um mock para simular a condição de corrida onde 
    # a query de contagem retorna 1 no momento da verificação.
    
    from unittest.mock import patch

    from tests.test_admin_routes import ROLE_ADMIN, _registrar_e_logar
    
    alvo, _ = _registrar_e_logar(client, db_session, "alvoadmin@teste.com", "100005", ROLE_ADMIN)

    with patch("sqlalchemy.orm.query.Query.scalar", return_value=1):
        res = client.patch(
            f"/admin/users/{alvo.id}/role",
            json={"role_nome": "aluno"},
            headers=headers,
        )

    assert res.status_code == 409
    assert "pelo menos um administrador ativo" in res.json()["detail"].lower()


# ── Testes de DELETE /admin/users/{user_id} ──────────────────

def test_delete_user_super_admin(client, super_admin_logado, aluno_logado):
    """Super Admin deve conseguir excluir (inativar) um usuário."""
    _super, token = super_admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/admin/users/{aluno.id}", headers=headers)

    assert res.status_code == 200
    assert "excluído" in res.json()["mensagem"].lower()


def test_delete_user_admin_bloqueado(client, admin_logado, aluno_logado):
    """Admin normal não pode excluir usuários (403)."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/admin/users/{aluno.id}", headers=headers)

    assert res.status_code == 403
    assert "permissão" in res.json()["detail"].lower() or "acesso negado" in res.json()["detail"].lower()
