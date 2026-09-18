"""
Testes de Integração — Rotas de Administração (/admin)
"""

import pytest

from app.models.user import User
from conftest import (
    CURSO_TESTE_ID,
    ROLE_ADMIN_ID,
    ROLE_ALUNO_ID,
    ROLE_SUPER_ADMIN_ID,
    STATUS_ATIVO_ID,
)

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
        "curso_id": str(CURSO_TESTE_ID),
    }
    client.post("/auth/register", json=payload)
    user = db_session.query(User).filter(User.email == email).first()
    user.status_id = STATUS_ATIVO_ID
    user.global_role = role_id
    db_session.commit()
    res_login = client.post(
        "/auth/login", json={"email": email, "senha": "SenhaForte123!"}
    )
    return user, res_login.json()["token_acesso"]


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def admin_logado(client, db_session):
    """Cria e loga um usuário com role 'admin'."""
    return _registrar_e_logar(
        client, db_session, "admin@teste.com", "100001", ROLE_ADMIN_ID
    )


@pytest.fixture
def super_admin_logado(client, db_session):
    """Cria e loga um usuário com role 'super_admin'."""
    return _registrar_e_logar(
        client, db_session, "super@teste.com", "100002", ROLE_SUPER_ADMIN_ID
    )


@pytest.fixture
def aluno_logado(client, db_session):
    """Cria e loga um usuário com role 'aluno'."""
    return _registrar_e_logar(
        client, db_session, "aluno@teste.com", "100003", ROLE_ALUNO_ID
    )


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
        "curso_id": str(CURSO_TESTE_ID),
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
    assert res.json()["detail"] == "Acesso negado. Nível de permissão insuficiente."


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
    assert res.json()["mensagem"] == "Status do usuário alterado para ativo com sucesso."


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
    assert res.json()["mensagem"] == "Status do usuário alterado para inativo com sucesso."


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


def test_change_status_admin_nao_altera_superadmin(
    client, admin_logado, super_admin_logado
):
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
    assert res.json()["detail"] == "Apenas outro super_admin pode alterar um super_admin."


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
    assert res.json()["detail"] == "Status inválido. Escolha 'ativo' ou 'inativo'."


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
    assert res.json()["mensagem"] == "Cargo do usuário alterado para 'admin' com sucesso."


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
    assert res.json()["detail"] == "Você não pode alterar o seu próprio cargo. Peça a outro administrador."


def test_change_role_admin_nao_rebaixa_superadmin(
    client, admin_logado, super_admin_logado
):
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
    assert res.json()["detail"] == "Apenas um super_admin pode alterar o cargo de outro super_admin."


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
    assert res.json()["detail"] == "Só é possível alterar o cargo de usuários com status ativo."


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

    alvo, _ = _registrar_e_logar(
        client, db_session, "alvoadmin@teste.com", "100005", ROLE_ADMIN_ID
    )

    with patch("sqlalchemy.orm.query.Query.scalar", return_value=1):
        res = client.patch(
            f"/admin/users/{alvo.id}/role",
            json={"role_nome": "aluno"},
            headers=headers,
        )

    assert res.status_code == 409
    assert res.json()["detail"] == "Operação negada. O sistema deve ter pelo menos um administrador ativo."


# ── Testes de DELETE /admin/users/{user_id} ──────────────────


def test_delete_user_super_admin(client, super_admin_logado, aluno_logado):
    """Super Admin deve conseguir excluir (inativar) um usuário."""
    _super, token = super_admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/admin/users/{aluno.id}", headers=headers)

    assert res.status_code == 200
    assert res.json()["mensagem"] == "Usuário excluído (inativado) com sucesso."


def test_delete_user_admin_bloqueado(client, admin_logado, aluno_logado):
    """Admin normal não pode excluir usuários (403)."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/admin/users/{aluno.id}", headers=headers)

    assert res.status_code == 403
    assert res.json()["detail"] == "Acesso negado. Nível de permissão insuficiente."
