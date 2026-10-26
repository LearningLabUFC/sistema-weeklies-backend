"""Testes de End Work Session."""


from uuid import UUID

from app.models.work_session import (
    MotivoEncerramento,
    WorkSession,
    WorkSessionStatus,
)

from .helpers import _headers


def test_end_work_session_sucesso(
    client,
    db_session,
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
    assert (
        data["motivo_encerramento"]
        == MotivoEncerramento.MANUAL.value
    )
    assert data["saida_em"] is not None

    sessao_salva = (
        db_session.query(WorkSession)
        .filter(
            WorkSession.id == UUID(sessao["id"])
        )
        .first()
    )

    assert sessao_salva is not None
    assert (
        sessao_salva.status
        == WorkSessionStatus.FINALIZADA
    )
    assert sessao_salva.saida is not None
    assert (
        sessao_salva.motivo_encerramento
        == MotivoEncerramento.MANUAL
    )

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

