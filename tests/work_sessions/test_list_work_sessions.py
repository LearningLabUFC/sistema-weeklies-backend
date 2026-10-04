"""Testes de List Work Sessions."""



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

