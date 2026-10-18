"""Testes de List Work Sessions."""

from app.core.constants import TestID

from .helpers import _headers


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


def _criar_sessao_finalizada_e_ativa(client, token):
    """Cria uma sessão FINALIZADA e, em seguida, uma nova sessão ATIVA."""
    primeira = client.post(
        "/work-sessions",
        json={"setor_id": str(TestID.SETOR_TESTE)},
        headers=_headers(token),
    )
    assert primeira.status_code == 201

    encerrada = client.patch(
        f"/work-sessions/{primeira.json()['id']}/end",
        headers=_headers(token),
    )
    assert encerrada.status_code == 200

    segunda = client.post(
        "/work-sessions",
        json={"setor_id": str(TestID.SETOR_TESTE)},
        headers=_headers(token),
    )
    assert segunda.status_code == 201

    return primeira.json()["id"], segunda.json()["id"]


def test_list_work_sessions_filtra_por_status_ativa(
    client,
    usuario_no_setor,
):
    _usuario, token = usuario_no_setor
    id_finalizada, id_ativa = _criar_sessao_finalizada_e_ativa(client, token)

    response = client.get(
        "/work-sessions",
        params={"status": "ATIVA"},
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()
    ids = [item["id"] for item in data["sessoes"]]

    assert data["total"] == 1
    assert ids == [id_ativa]
    assert id_finalizada not in ids
    assert all(item["status"] == "ATIVA" for item in data["sessoes"])


def test_list_work_sessions_filtra_por_status_finalizada(
    client,
    usuario_no_setor,
):
    _usuario, token = usuario_no_setor
    id_finalizada, id_ativa = _criar_sessao_finalizada_e_ativa(client, token)

    response = client.get(
        "/work-sessions",
        params={"status": "FINALIZADA"},
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()
    ids = [item["id"] for item in data["sessoes"]]

    assert data["total"] == 1
    assert ids == [id_finalizada]
    assert id_ativa not in ids
    assert all(item["status"] == "FINALIZADA" for item in data["sessoes"])


def test_list_work_sessions_sem_filtro_status_retorna_todas(
    client,
    usuario_no_setor,
):
    _usuario, token = usuario_no_setor
    id_finalizada, id_ativa = _criar_sessao_finalizada_e_ativa(client, token)

    response = client.get(
        "/work-sessions",
        headers=_headers(token),
    )

    assert response.status_code == 200

    ids = {item["id"] for item in response.json()["sessoes"]}

    assert {id_finalizada, id_ativa} <= ids


def test_list_work_sessions_status_invalido_retorna_422(
    client,
    usuario_no_setor,
):
    _usuario, token = usuario_no_setor

    response = client.get(
        "/work-sessions",
        params={"status": "INEXISTENTE"},
        headers=_headers(token),
    )

    assert response.status_code == 422
