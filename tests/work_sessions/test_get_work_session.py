"""Testes de Get Work Session."""


from app.models.work_session import (
    WorkSessionStatus,
)

from .helpers import _headers


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

