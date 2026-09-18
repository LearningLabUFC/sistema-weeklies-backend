"""
Testes de Integração — Rotas de Setores (/sectors)
"""

import uuid

import pytest

from app.models.user import User
from conftest import (
    CURSO_TESTE_ID,
    ROLE_ADMIN_ID,
    ROLE_ALUNO_ID,
    ROLE_SUPER_ADMIN_ID,
    SETOR_TESTE_ID,
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
        client, db_session, "secadmin@teste.com", "200001", ROLE_ADMIN_ID
    )


@pytest.fixture
def super_admin_logado(client, db_session):
    """Cria e loga um usuário com role 'super_admin'."""
    return _registrar_e_logar(
        client, db_session, "secsuper@teste.com", "200002", ROLE_SUPER_ADMIN_ID
    )


@pytest.fixture
def aluno_logado(client, db_session):
    """Cria e loga um usuário com role 'aluno'."""
    return _registrar_e_logar(
        client, db_session, "secaluno@teste.com", "200003", ROLE_ALUNO_ID
    )


@pytest.fixture
def membro_extra(client, db_session):
    """Cria um segundo membro para associação com setor."""
    return _registrar_e_logar(
        client, db_session, "secmembro@teste.com", "200004", ROLE_ALUNO_ID
    )


# ── Testes de POST /sectors ─────────────────────────────────


def test_create_sector_admin(client, admin_logado):
    """Admin deve conseguir criar um setor."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/sectors",
        json={"nome": "Marketing", "descricao": "Setor de marketing digital."},
        headers=headers,
    )

    assert res.status_code == 201
    # Mensagem dinâmica: f"Setor '{nome}' criado com sucesso."
    assert "com sucesso" in res.json()["mensagem"]


def test_create_sector_duplicado(client, admin_logado):
    """Criar setor com nome duplicado deve retornar 409."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/sectors",
        json={"nome": "Duplicado"},
        headers=headers,
    )
    res = client.post(
        "/sectors",
        json={"nome": "Duplicado"},
        headers=headers,
    )

    assert res.status_code == 409


def test_create_sector_aluno_bloqueado(client, aluno_logado):
    """Alunos NÃO podem criar setores (403)."""
    _user, token = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/sectors",
        json={"nome": "Bloqueado"},
        headers=headers,
    )

    assert res.status_code == 403


# ── Testes de GET /sectors ───────────────────────────────────


def test_list_sectors_admin(client, admin_logado):
    """Admin deve conseguir listar setores com paginação."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/sectors", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert "setores" in data
    assert "total" in data
    assert data["pagina"] == 1


def test_list_sectors_super_admin(client, super_admin_logado):
    """Super Admin deve conseguir listar setores."""
    _user, token = super_admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/sectors", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert "setores" in data


def test_list_sectors_aluno(client, aluno_logado):
    """Aluno (Membro) deve conseguir listar setores (apenas saber que existem)."""
    _user, token = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/sectors", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert "setores" in data


# ── Testes de GET /sectors/{sector_id} ───────────────────────


def test_get_sector_detail(client, admin_logado):
    """Admin deve conseguir ver detalhes de um setor."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get(f"/sectors/{SETOR_TESTE_ID}", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["nome"] == "Desenvolvimento Teste"
    assert "membros" in data


def test_get_sector_detail_aluno(client, aluno_logado):
    """Aluno não deve conseguir ver detalhes do setor (403)."""
    _user, token = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get(f"/sectors/{SETOR_TESTE_ID}", headers=headers)

    assert res.status_code == 403


def test_get_sector_not_found(client, admin_logado):
    """Setor inexistente deve retornar 404."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    fake_id = uuid.uuid4()
    res = client.get(f"/sectors/{fake_id}", headers=headers)

    assert res.status_code == 404


# ── Testes de PATCH /sectors/{sector_id} ─────────────────────


def test_update_sector(client, admin_logado):
    """Admin deve conseguir atualizar um setor."""
    _user, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/sectors/{SETOR_TESTE_ID}",
        json={"descricao": "Nova descrição do setor."},
        headers=headers,
    )

    assert res.status_code == 200
    assert res.json()["mensagem"] == "Setor atualizado com sucesso."


# ── Testes de DELETE /sectors/{sector_id} ────────────────────


def test_delete_sector_super_admin(client, super_admin_logado):
    """Super Admin deve conseguir desativar um setor."""
    _super, token = super_admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    # Criar setor para desativar
    client.post(
        "/sectors",
        json={"nome": "Setor Para Desativar"},
        headers=headers,
    )

    # Buscar o setor criado
    res_list = client.get("/sectors", headers=headers)
    setor = next(
        s for s in res_list.json()["setores"] if s["nome"] == "Setor Para Desativar"
    )

    res = client.delete(f"/sectors/{setor['id']}", headers=headers)

    assert res.status_code == 200
    assert res.json()["mensagem"] == "Setor desativado com sucesso."


def test_delete_sector_admin_bloqueado(client, admin_logado):
    """Admin normal não pode desativar setores (403)."""
    _admin, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/sectors/{SETOR_TESTE_ID}", headers=headers)

    assert res.status_code == 403


# ── Testes de POST /sectors/{sector_id}/members ──────────────


def test_add_member_to_sector(client, admin_logado, aluno_logado):
    """Admin deve conseguir adicionar um membro a um setor."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "membro"},
        headers=headers,
    )

    assert res.status_code == 201
    # Mensagem dinâmica: f"Usuário adicionado ao setor como '{papel}' com sucesso."
    assert "com sucesso" in res.json()["mensagem"]


def test_add_member_duplicado(client, admin_logado, aluno_logado):
    """Adicionar membro já existente deve retornar 409."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    # Adiciona pela primeira vez
    client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "membro"},
        headers=headers,
    )

    # Tenta adicionar novamente
    res = client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "membro"},
        headers=headers,
    )

    assert res.status_code == 409


def test_add_member_papel_invalido(client, admin_logado, aluno_logado):
    """Papel inválido deve retornar 400."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "invalido"},
        headers=headers,
    )

    assert res.status_code == 400


def test_add_leader_to_sector(client, admin_logado, membro_extra):
    """Admin deve conseguir adicionar um líder a um setor."""
    _admin, token = admin_logado
    membro, _ = membro_extra
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(membro.id), "papel": "lider"},
        headers=headers,
    )

    assert res.status_code == 201
    # Mensagem dinâmica: f"Usuário adicionado ao setor como '{papel}' com sucesso."
    assert "lider" in res.json()["mensagem"]


# ── Testes de DELETE /sectors/{sector_id}/members/{user_id} ──


def test_remove_member_from_sector(client, admin_logado, aluno_logado):
    """Admin deve conseguir remover um membro de um setor."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    # Adicionar membro primeiro
    client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "membro"},
        headers=headers,
    )

    # Remover
    res = client.delete(
        f"/sectors/{SETOR_TESTE_ID}/members/{aluno.id}",
        headers=headers,
    )

    assert res.status_code == 200
    assert res.json()["mensagem"] == "Usuário removido do setor com sucesso."


def test_remove_member_not_found(client, admin_logado):
    """Remover membro não associado deve retornar 404."""
    _admin, token = admin_logado
    headers = {"Authorization": f"Bearer {token}"}

    fake_user_id = uuid.uuid4()
    res = client.delete(
        f"/sectors/{SETOR_TESTE_ID}/members/{fake_user_id}",
        headers=headers,
    )

    assert res.status_code == 404


# ── Testes de PATCH /sectors/{sector_id}/members/{user_id}/role ──


def test_change_member_role(client, admin_logado, aluno_logado):
    """Admin deve conseguir alterar o papel de um membro no setor."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    # Adicionar como membro
    client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "membro"},
        headers=headers,
    )

    # Promover a líder
    res = client.patch(
        f"/sectors/{SETOR_TESTE_ID}/members/{aluno.id}/role",
        json={"papel": "lider"},
        headers=headers,
    )

    assert res.status_code == 200
    # Mensagem dinâmica: f"Papel do usuário alterado para '{papel}' com sucesso."
    assert "lider" in res.json()["mensagem"]


def test_change_role_same_papel(client, admin_logado, aluno_logado):
    """Alterar para o mesmo papel deve retornar 400."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    # Adicionar como membro
    client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "membro"},
        headers=headers,
    )

    # Tentar manter como membro
    res = client.patch(
        f"/sectors/{SETOR_TESTE_ID}/members/{aluno.id}/role",
        json={"papel": "membro"},
        headers=headers,
    )

    assert res.status_code == 400


# ── Testes de verificação do detalhe com membros ─────────────


def test_sector_detail_with_members(client, admin_logado, aluno_logado):
    """O detalhe do setor deve incluir membros adicionados."""
    _admin, token = admin_logado
    aluno, _ = aluno_logado
    headers = {"Authorization": f"Bearer {token}"}

    # Adicionar membro
    client.post(
        f"/sectors/{SETOR_TESTE_ID}/members",
        json={"usuario_id": str(aluno.id), "papel": "membro"},
        headers=headers,
    )

    # Ver detalhe
    res = client.get(f"/sectors/{SETOR_TESTE_ID}", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert len(data["membros"]) >= 1
    emails = [m["email"] for m in data["membros"]]
    assert "secaluno@teste.com" in emails
