"""Testes de Start Work Session."""


from uuid import UUID

from app.core.constants import TestID
from app.models.work_session import (
    WorkSession,
    WorkSessionStatus,
)

from .helpers import _headers


def test_start_work_session_sucesso(
    client,
    db_session,
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

    sessao_salva = (
        db_session.query(WorkSession)
        .filter(
            WorkSession.id == UUID(data["id"])
        )
        .first()
    )

    assert sessao_salva is not None
    assert sessao_salva.usuario_id == usuario.id
    assert sessao_salva.setor_id == TestID.SETOR_TESTE
    assert sessao_salva.status == WorkSessionStatus.ATIVA
    assert sessao_salva.saida is None
    assert sessao_salva.entrada is not None
    assert sessao_salva.expiracao is not None

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

