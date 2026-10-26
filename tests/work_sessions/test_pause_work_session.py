"""Testes de Pause Work Session."""



from uuid import UUID

from app.models.pause import Pause
from app.models.work_session import WorkSession, WorkSessionStatus

from .helpers import _headers


def test_start_pause_sucesso(
    client,
    db_session,
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

    pausa_salva = (
        db_session.query(Pause)
        .filter(
            Pause.id == UUID(data["id"])
        )
        .first()
    )

    assert pausa_salva is not None
    assert (
        pausa_salva.sessao_trabalho_id
        == UUID(sessao["id"])
    )
    assert pausa_salva.inicio is not None
    assert pausa_salva.fim is None

    sessao_salva = (
        db_session.query(WorkSession)
        .filter(
            WorkSession.id == UUID(sessao["id"])
        )
        .first()
    )

    assert sessao_salva is not None
    assert sessao_salva.status == WorkSessionStatus.EM_PAUSA

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
    db_session,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    pause_response = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert pause_response.status_code == 201

    pausa = pause_response.json()

    response = client.patch(
        (
            f"/work-sessions/{sessao['id']}"
            f"/pauses/{pausa['id']}/end"
        ),
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["fim_em"] is not None

    pausa_salva = (
        db_session.query(Pause)
        .filter(
            Pause.id == UUID(pausa["id"])
        )
        .first()
    )

    assert pausa_salva is not None
    assert pausa_salva.fim is not None

    sessao_salva = (
        db_session.query(WorkSession)
        .filter(
            WorkSession.id == UUID(sessao["id"])
        )
        .first()
    )

    assert sessao_salva is not None
    assert sessao_salva.status == WorkSessionStatus.ATIVA