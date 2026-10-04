"""Testes de Pause Work Session."""



from .helpers import _headers


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

