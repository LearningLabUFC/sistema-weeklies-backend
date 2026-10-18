"""Testes de Work Session Summary."""

from datetime import datetime, timedelta, timezone

from .helpers import _headers


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

