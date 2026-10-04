"""Testes de Continue Work Session."""

from datetime import datetime, timedelta, timezone

from .helpers import _buscar_sessao, _headers


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

