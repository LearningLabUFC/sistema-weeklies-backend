"""Testes de Continue Work Session."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.config import settings
from app.models.work_session import WorkSession

from .helpers import _buscar_sessao, _headers


def test_continue_work_session_sucesso_na_janela(
    client,
    db_session,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    sessao_salva = (
        db_session.query(WorkSession)
        .filter(
            WorkSession.id == UUID(sessao["id"])
        )
        .first()
    )

    assert sessao_salva is not None

    sessao_salva.expiracao = (
        datetime.now(timezone.utc)
        + timedelta(minutes=5)
    )

    db_session.commit()
    db_session.refresh(sessao_salva)

    expiracao_anterior = sessao_salva.expiracao

    response = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert response.status_code == 200

    db_session.refresh(sessao_salva)

    expiracao_esperada = (
        expiracao_anterior
        + timedelta(
            hours=settings.WORK_SESSION_EXTENSION_HOURS
        )
    )

    assert sessao_salva.expiracao == expiracao_esperada

    data = response.json()

    assert data["id"] == sessao["id"]
    assert data["expira_em"] is not None

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

