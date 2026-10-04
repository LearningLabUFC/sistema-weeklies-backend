"""
Testes de Integração — Rotas de Sessões de Trabalho (/work-sessions).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.core.constants import RoleID, StatusID, TestID
from app.models.sector_user import SectorUser
from app.models.user import User
from app.models.work_session import (
    MotivoEncerramento,
    WorkSession,
    WorkSessionStatus,
)

# ── Helpers ──────────────────────────────────────────────────


def _registrar_e_logar(
    client,
    db_session,
    email: str,
    matricula: str,
    role_id,
):
    """Registra, ativa, define o papel global e autentica um usuário."""
    payload = {
        "nome_completo": f"Teste {email.split('@')[0].title()}",
        "email": email,
        "senha": "SenhaForte123!",
        "matricula": matricula,
        "data_nascimento": "2000-01-01",
        "meta_horas_semanais": 12,
        "curso_id": str(TestID.CURSO_TESTE),
    }

    client.post("/auth/register", json=payload)

    user = (
        db_session.query(User)
        .filter(User.email == email)
        .first()
    )
    user.status_id = StatusID.ATIVO
    user.global_role = role_id
    db_session.commit()

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "senha": "SenhaForte123!",
        },
    )

    return user, response.json()["token_acesso"]


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def _adicionar_ao_setor(
    db_session,
    usuario: User,
    papel: str = "membro",
) -> SectorUser:
    vinculo = SectorUser(
        setor_id=TestID.SETOR_TESTE,
        usuario_id=usuario.id,
        papel=papel,
    )
    db_session.add(vinculo)
    db_session.commit()
    db_session.refresh(vinculo)
    return vinculo


def _buscar_sessao(
    db_session,
    session_id: str,
) -> WorkSession:
    return (
        db_session.query(WorkSession)
        .filter(
            WorkSession.id == UUID(session_id),
        )
        .first()
    )


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def admin_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "workadmin@teste.com",
        "300001",
        RoleID.ADMIN,
    )


@pytest.fixture
def super_admin_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "worksuper@teste.com",
        "300002",
        RoleID.SUPER_ADMIN,
    )


@pytest.fixture
def usuario_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "workuser@teste.com",
        "300003",
        RoleID.USUARIO,
    )


@pytest.fixture
def outro_usuario_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "workother@teste.com",
        "300004",
        RoleID.USUARIO,
    )


@pytest.fixture
def usuario_no_setor(
    db_session,
    usuario_logado,
):
    usuario, token = usuario_logado
    _adicionar_ao_setor(
        db_session,
        usuario,
        "membro",
    )
    return usuario, token


@pytest.fixture
def outro_usuario_no_setor(
    db_session,
    outro_usuario_logado,
):
    usuario, token = outro_usuario_logado
    _adicionar_ao_setor(
        db_session,
        usuario,
        "membro",
    )
    return usuario, token


@pytest.fixture
def lider_logado(
    db_session,
    client,
):
    usuario, token = _registrar_e_logar(
        client,
        db_session,
        "worklider@teste.com",
        "300005",
        RoleID.USUARIO,
    )
    _adicionar_ao_setor(
        db_session,
        usuario,
        "lider",
    )
    return usuario, token


@pytest.fixture
def sessao_ativa(
    client,
    usuario_no_setor,
):
    usuario, token = usuario_no_setor

    response = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    assert response.status_code == 201

    return usuario, token, response.json()


# ── POST /work-sessions ──────────────────────────────────────


def test_start_work_session_sucesso(
    client,
    usuario_no_setor,
):
    usuario, token = usuario_no_setor

    response = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["usuario_id"] == str(usuario.id)
    assert data["setor_id"] == str(TestID.SETOR_TESTE)
    assert data["status"] == WorkSessionStatus.ATIVA.value
    assert data["saida_em"] is None
    assert data["motivo_encerramento"] is None
    assert data["tempo_trabalhado_segundos"] == 0
    assert data["expira_em"] is not None


def test_start_work_session_sem_vinculo_com_setor(
    client,
    usuario_logado,
):
    _usuario, token = usuario_logado

    response = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    assert response.status_code == 403


def test_start_work_session_rejeita_segunda_sessao(
    client,
    usuario_no_setor,
):
    _usuario, token = usuario_no_setor

    primeira = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    segunda = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 409


def test_start_work_session_sem_token(client):
    response = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
    )

    assert response.status_code == 403


def test_admin_nao_pode_bater_ponto(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    response = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    assert response.status_code == 403


def test_super_admin_nao_pode_bater_ponto(
    client,
    super_admin_logado,
):
    _super_admin, token = super_admin_logado

    response = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    assert response.status_code == 403


# ── GET /work-sessions/current ───────────────────────────────


def test_get_current_sem_sessao(
    client,
    usuario_logado,
):
    _usuario, token = usuario_logado

    response = client.get(
        "/work-sessions/current",
        headers=_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["sessao"] is None


def test_get_current_com_sessao(
    client,
    sessao_ativa,
):
    usuario, token, sessao = sessao_ativa

    response = client.get(
        "/work-sessions/current",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["sessao"] is not None
    assert data["sessao"]["id"] == sessao["id"]
    assert data["sessao"]["usuario_id"] == str(usuario.id)
    assert data["sessao"]["status"] == WorkSessionStatus.ATIVA.value


# ── Pausas ───────────────────────────────────────────────────


def test_start_pause_sucesso(
    client,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    response = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["sessao_id"] == sessao["id"]
    assert data["inicio_em"] is not None
    assert data["fim_em"] is None


def test_start_pause_rejeita_segunda_pausa(
    client,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    primeira = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    segunda = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 409


def test_end_pause_sucesso(
    client,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    pause_response = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert pause_response.status_code == 201

    pause = pause_response.json()

    response = client.patch(
        (
            f"/work-sessions/{sessao['id']}"
            f"/pauses/{pause['id']}/end"
        ),
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == pause["id"]
    assert data["fim_em"] is not None


# ── PATCH /work-sessions/{id}/continue ───────────────────────


def test_continue_work_session_sucesso_na_janela(
    client,
    db_session,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )

    work_session.expiracao = (
        datetime.now(timezone.utc)
        + timedelta(minutes=5)
    )
    db_session.commit()
    db_session.refresh(work_session)

    expiracao_anterior = work_session.expiracao

    response = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    expiracao_nova = datetime.fromisoformat(
        data["expira_em"].replace(
            "Z",
            "+00:00",
        )
    )

    assert expiracao_nova > expiracao_anterior


def test_continue_work_session_fora_da_janela(
    client,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    response = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert response.status_code == 409


def test_continue_work_session_pode_prorrogar_novamente(
    client,
    db_session,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )

    work_session.expiracao = (
        datetime.now(timezone.utc)
        + timedelta(minutes=5)
    )
    db_session.commit()

    primeira = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert primeira.status_code == 200

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.expiracao = (
        datetime.now(timezone.utc)
        + timedelta(minutes=5)
    )
    db_session.commit()

    segunda = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert segunda.status_code == 200


# ── PATCH /work-sessions/{id}/end ────────────────────────────


def test_end_work_session_sucesso(
    client,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    response = client.patch(
        f"/work-sessions/{sessao['id']}/end",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == WorkSessionStatus.FINALIZADA.value
    assert data["motivo_encerramento"] == MotivoEncerramento.MANUAL.value
    assert data["saida_em"] is not None


def test_end_work_session_em_pausa_fecha_pausa(
    client,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    pause_response = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert pause_response.status_code == 201

    response = client.patch(
        f"/work-sessions/{sessao['id']}/end",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == WorkSessionStatus.FINALIZADA.value

    detail = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token),
    )

    assert detail.status_code == 200
    assert len(detail.json()["pausas"]) == 1
    assert detail.json()["pausas"][0]["fim_em"] is not None


def test_end_work_session_rejeita_sessao_de_outro_usuario(
    client,
    sessao_ativa,
    outro_usuario_logado,
):
    _dono, _token_dono, sessao = sessao_ativa
    _outro, token_outro = outro_usuario_logado

    response = client.patch(
        f"/work-sessions/{sessao['id']}/end",
        headers=_headers(token_outro),
    )

    assert response.status_code == 403


# ── GET /work-sessions/{id} ──────────────────────────────────


def test_get_work_session_propria(
    client,
    sessao_ativa,
):
    usuario, token, sessao = sessao_ativa

    response = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == sessao["id"]
    assert data["usuario_id"] == str(usuario.id)


def test_get_work_session_usuario_comum_bloqueado(
    client,
    sessao_ativa,
    outro_usuario_logado,
):
    _usuario, _token, sessao = sessao_ativa
    _outro, token_outro = outro_usuario_logado

    response = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token_outro),
    )

    assert response.status_code == 403


def test_get_work_session_admin_pode_consultar(
    client,
    sessao_ativa,
    admin_logado,
):
    _usuario, _token_usuario, sessao = sessao_ativa
    _admin, token_admin = admin_logado

    response = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token_admin),
    )

    assert response.status_code == 200


def test_get_work_session_super_admin_pode_consultar(
    client,
    sessao_ativa,
    super_admin_logado,
):
    _usuario, _token_usuario, sessao = sessao_ativa
    _super_admin, token_super_admin = super_admin_logado

    response = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token_super_admin),
    )

    assert response.status_code == 200


def test_get_work_session_lider_pode_consultar_setor(
    client,
    sessao_ativa,
    lider_logado,
):
    _usuario, _token_usuario, sessao = sessao_ativa
    _lider, token_lider = lider_logado

    response = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token_lider),
    )

    assert response.status_code == 200


# ── GET /work-sessions ───────────────────────────────────────


def test_list_work_sessions_proprias(
    client,
    sessao_ativa,
):
    usuario, token, _sessao = sessao_ativa

    response = client.get(
        "/work-sessions",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] >= 1
    assert data["pagina"] == 1
    assert data["limite"] == 20
    assert all(
        item["usuario_id"] == str(usuario.id)
        for item in data["sessoes"]
    )


def test_admin_lista_sessoes_de_todos(
    client,
    sessao_ativa,
    admin_logado,
):
    usuario, _token_usuario, sessao = sessao_ativa
    _admin, token_admin = admin_logado

    response = client.get(
        "/work-sessions",
        headers=_headers(token_admin),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] >= 1
    assert any(
        item["id"] == sessao["id"]
        and item["usuario_id"] == str(usuario.id)
        for item in data["sessoes"]
    )


def test_super_admin_lista_sessoes_de_todos(
    client,
    sessao_ativa,
    super_admin_logado,
):
    usuario, _token_usuario, sessao = sessao_ativa
    _super_admin, token_super_admin = super_admin_logado

    response = client.get(
        "/work-sessions",
        headers=_headers(token_super_admin),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] >= 1
    assert any(
        item["id"] == sessao["id"]
        and item["usuario_id"] == str(usuario.id)
        for item in data["sessoes"]
    )


# ── GET /work-sessions/summary ───────────────────────────────


def test_summary_periodo_invalido(
    client,
    usuario_logado,
):
    _usuario, token = usuario_logado

    agora = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/summary",
        params={
            "inicio": agora.isoformat(),
            "fim": (
                agora - timedelta(hours=1)
            ).isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 400


def test_summary_sucesso(
    client,
    sessao_ativa,
):
    usuario, token, _sessao = sessao_ativa

    agora = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/summary",
        params={
            "inicio": (
                agora - timedelta(hours=1)
            ).isoformat(),
            "fim": (
                agora + timedelta(hours=1)
            ).isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["usuario_id"] == str(usuario.id)
    assert data["tempo_trabalhado_segundos"] >= 0


def test_admin_summary_de_todos(
    client,
    sessao_ativa,
    admin_logado,
):
    _usuario, _token_usuario, _sessao = sessao_ativa
    _admin, token_admin = admin_logado

    agora = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/summary",
        params={
            "inicio": (
                agora - timedelta(hours=1)
            ).isoformat(),
            "fim": (
                agora + timedelta(hours=1)
            ).isoformat(),
        },
        headers=_headers(token_admin),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["usuario_id"] is None
    assert data["tempo_trabalhado_segundos"] >= 0

def test_metrics_summary_admin_sucesso(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/summary",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert "tempo_trabalhado_segundos" in data
    assert "tempo_pausado_segundos" in data
    assert "sessoes_iniciadas" in data
    assert "usuarios_com_tempo_trabalhado" in data

def test_metrics_usuario_comum_retorna_403(
    client,
    usuario_logado,
):
    _usuario, token = usuario_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/summary",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 403

def test_metrics_periodo_invalido(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    agora = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/metrics/summary",
        params={
            "inicio": agora.isoformat(),
            "fim": (
                agora - timedelta(hours=1)
            ).isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 400

def test_metrics_users_admin_sucesso(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/users",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert "usuarios" in data
    assert "total" in data
    assert data["pagina"] == 1
    assert data["limite"] == 20

def test_metrics_sectors_admin_sucesso(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/sectors",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert "setores" in data
    assert "total" in data
