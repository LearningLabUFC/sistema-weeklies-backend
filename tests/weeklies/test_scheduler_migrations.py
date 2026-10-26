"""Exercita o esquema entregue por Alembic, incluindo bancos já instalados."""

from datetime import date
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command
from app.models.weekly_scheduler_execution import WeeklySchedulerExecution
from app.weeklies.scheduler import registrar_execucao_job


@pytest.fixture
def migration_db(db_session):
    # Esquema exclusivo em transação reversível; nunca altera tabelas da aplicação.
    with db_session.get_bind().engine.connect() as connection:
        transaction = connection.begin()
        schema = "migration_test_" + uuid4().hex
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        try:
            yield connection, config
        finally:
            transaction.rollback()


def test_upgrade_preserva_historico_e_permite_registro_orm(migration_db):
    connection, config = migration_db
    command.upgrade(config, "9176f5980bb7")
    connection.execute(
        sa.text(
            "INSERT INTO weekly_scheduler_execucoes (tipo, semana_referencia) "
            "VALUES ('CRIAR_WEEKLIES', '2026-10-05')"
        )
    )
    command.upgrade(config, "head")
    with Session(bind=connection) as db:
        anterior = db.query(WeeklySchedulerExecution).one()
        assert isinstance(anterior.id, UUID)
        assert anterior.semana_referencia == date(2026, 10, 5)
        registrar_execucao_job(db, "VERIFICAR_AUSENCIAS", date(2026, 10, 5))
        assert db.query(WeeklySchedulerExecution).count() == 2

    command.downgrade(config, "9176f5980bb7")
    assert (
        connection.execute(
            sa.text("SELECT count(*) FROM weekly_scheduler_execucoes")
        ).scalar()
        == 2
    )
    connection.execute(
        sa.text(
            "INSERT INTO weekly_scheduler_execucoes (tipo, semana_referencia) "
            "VALUES ('CRIAR_WEEKLIES', '2026-10-12')"
        )
    )
    command.upgrade(config, "head")
    with Session(bind=connection) as db:
        assert db.query(WeeklySchedulerExecution).count() == 3


@pytest.mark.parametrize("legacy_schema", ["missing", "uuid"])
def test_upgrade_instalacoes_anteriores_ao_historico(migration_db, legacy_schema):
    connection, config = migration_db
    command.upgrade(config, "9176f5980bb7")
    connection.execute(sa.text("DROP TABLE weekly_scheduler_execucoes"))
    if legacy_schema == "uuid":
        WeeklySchedulerExecution.__table__.create(connection)
    command.upgrade(config, "head")
    with Session(bind=connection) as db:
        registrar_execucao_job(db, "CRIAR_WEEKLIES", date(2026, 10, 5))
        assert isinstance(db.query(WeeklySchedulerExecution).one().id, UUID)
