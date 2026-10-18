"""Fixtures compartilhadas pelos testes de work sessions."""

import pytest

from app.core.constants import RoleID, TestID

from .helpers import _adicionar_ao_setor, _headers, _registrar_e_logar


@pytest.fixture
def admin_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "workadmin@teste.com",
        "300001",
        RoleID.ADMIN,
    )

@pytest.fixture
def super_admin_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "worksuper@teste.com",
        "300002",
        RoleID.SUPER_ADMIN,
    )

@pytest.fixture
def usuario_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "workuser@teste.com",
        "300003",
        RoleID.USUARIO,
    )

@pytest.fixture
def outro_usuario_logado(client, db_session):
    return _registrar_e_logar(
        client,
        db_session,
        "workother@teste.com",
        "300004",
        RoleID.USUARIO,
    )

@pytest.fixture
def usuario_no_setor(
    db_session,
    usuario_logado,
):
    usuario, token = usuario_logado
    _adicionar_ao_setor(
        db_session,
        usuario,
        "membro",
    )
    return usuario, token

@pytest.fixture
def outro_usuario_no_setor(
    db_session,
    outro_usuario_logado,
):
    usuario, token = outro_usuario_logado
    _adicionar_ao_setor(
        db_session,
        usuario,
        "membro",
    )
    return usuario, token

@pytest.fixture
def lider_logado(
    db_session,
    client,
):
    usuario, token = _registrar_e_logar(
        client,
        db_session,
        "worklider@teste.com",
        "300005",
        RoleID.USUARIO,
    )
    _adicionar_ao_setor(
        db_session,
        usuario,
        "lider",
    )
    return usuario, token

@pytest.fixture
def sessao_ativa(
    client,
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

    return usuario, token, response.json()

