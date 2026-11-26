"""Testes automatizados do script utilitário scripts/seed_dev.py."""

from datetime import date

import pytest

from app.auth.schemas import LoginRequest
from app.core.constants import RoleID, StatusID
from app.core.security import hash_senha, verificar_senha
from app.core.validators import _MATRICULA_REGEX, _SENHA_REGEX, _validar_nome_completo
from app.models.course import Course
from app.models.sector_user import SectorUser
from app.models.user import User
from app.models.work_session import WorkSession, WorkSessionStatus
from scripts.seed_dev import (
    DEV_DEFAULT_PASSWORD,
    DEV_EMAIL_DOMAIN,
    PERSONAS,
    clean_dev_data,
    seed_dev_data,
    validar_ambiente_seguro,
)


def test_trava_ambiente_rejeita_producao():
    with pytest.raises(RuntimeError, match="Execução bloqueada: ambiente"):
        validar_ambiente_seguro(
            database_url="postgresql+psycopg://u:p@localhost:5432/db",
            environment="production",
        )


def test_trava_ambiente_rejeita_host_remoto():
    with pytest.raises(RuntimeError, match="host do banco"):
        validar_ambiente_seguro(
            database_url="postgresql+psycopg://u:p@ep-prod.aws.neon.tech:5432/db",
            environment="development",
        )


def test_trava_ambiente_aceita_localhost_em_dev():
    validar_ambiente_seguro(
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        environment="development",
    )


def test_personas_respeitam_validadores_da_api():
    assert _SENHA_REGEX.match(DEV_DEFAULT_PASSWORD)

    for spec in PERSONAS:
        assert _validar_nome_completo(spec.nome_completo) == spec.nome_completo
        assert _MATRICULA_REGEX.match(spec.matricula)
        payload = LoginRequest(email=spec.email, senha=DEV_DEFAULT_PASSWORD)
        assert payload.email == spec.email


def test_seed_dev_idempotente_e_clean_preserva_usuarios_reais(db_session):
    curso = db_session.query(Course).first()
    usuario_real = User(
        nome_completo="Membro Real Preservado",
        email="membro.real@learninglab.com.br",
        senha_hash=hash_senha("Real@1234"),
        matricula="123456",
        data_nascimento=date(2001, 5, 10),
        data_ingresso=date(2025, 1, 10),
        meta_horas_semanais=12,
        curso_id=curso.id,
        status_id=StatusID.ATIVO,
        global_role=RoleID.USUARIO,
    )
    db_session.add(usuario_real)
    db_session.commit()

    # 1ª execução cria todas as personas
    primeira = seed_dev_data(db_session)
    assert primeira["criados"] == len(PERSONAS)
    assert primeira["existentes"] == 0

    # 2ª execução é 100% idempotente
    segunda = seed_dev_data(db_session)
    assert segunda["criados"] == 0
    assert segunda["existentes"] == len(PERSONAS)
    assert segunda["vinculos_criados"] == 0

    admin_membro = (
        db_session.query(User)
        .filter(User.email == f"admin.membro{DEV_EMAIL_DOMAIN}")
        .first()
    )
    assert admin_membro is not None
    assert verificar_senha(DEV_DEFAULT_PASSWORD, admin_membro.senha_hash)

    vinculos_admin_membro = (
        db_session.query(SectorUser)
        .filter(SectorUser.usuario_id == admin_membro.id)
        .all()
    )
    assert len(vinculos_admin_membro) == 1
    assert vinculos_admin_membro[0].papel == "membro"

    # Simula uma sessão de trabalho criada durante teste manual para validar --clean
    sessao = WorkSession(
        usuario_id=admin_membro.id,
        setor_id=vinculos_admin_membro[0].setor_id,
        entrada=admin_membro.senha_atualizada_em,
        expiracao=admin_membro.senha_atualizada_em,
        status=WorkSessionStatus.ATIVA,
    )
    db_session.add(sessao)
    db_session.commit()

    # --clean remove apenas os mocks e preserva o usuário real
    removidos = clean_dev_data(db_session)
    assert removidos == len(PERSONAS)

    assert (
        db_session.query(User)
        .filter(User.email.like(f"%{DEV_EMAIL_DOMAIN}"))
        .count()
    ) == 0
    assert (
        db_session.query(User)
        .filter(User.email == "membro.real@learninglab.com.br")
        .first()
    ) is not None
