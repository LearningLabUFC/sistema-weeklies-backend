from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.core.constants import TestID
from app.models.sector_user import SectorUser
from app.models.weekly import Weekly
from app.models.weekly_scheduler_execution import WeeklySchedulerExecution
from app.models.weekly_warning import WeeklyWarning
from app.weeklies import scheduler
from app.weeklies.timezone_utils import FUSO_LLAB
from tests.weeklies.test_scheduler import _criar_membro


@pytest.fixture
def recovery_db(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_advertencia", lambda **kwargs: None
    )
    monkeypatch.setattr(settings, "WEEKLY_MARCO_IMPLANTACAO", None)
    # Commits e rollbacks reais dos serviços não desfazem os dados já preparados.
    with Session(
        bind=db_session.get_bind(),
        join_transaction_mode="create_savepoint",
        autoflush=False,
    ) as db:
        yield db


def test_criacao_parcial_permanece_pendente_e_recupera_so_faltantes(
    recovery_db, monkeypatch
):
    db = recovery_db
    monkeypatch.setattr(settings, "WEEKLY_MARCO_IMPLANTACAO", date(2026, 10, 2))
    membros = [
        _criar_membro(db, f"Membro {n}", f"retry{n}@test.com", f"RETRY{n}")
        for n in range(2)
    ]
    failed_id = membros[0].id
    real_create = scheduler.criar_weekly_com_rollover

    def fail_one(db, user_id, sector_id, week):
        if user_id == failed_id:
            raise RuntimeError("Falha transitória")
        return real_create(db, user_id, sector_id, week)

    monkeypatch.setattr(scheduler, "criar_weekly_com_rollover", fail_one)
    week = date(2026, 10, 12)
    result = scheduler.executar_criacao_weeklies_lote(db, week)
    assert result["erros"] == 1
    assert result["criadas"] == 1
    assert not scheduler.foi_executado(db, "CRIAR_WEEKLIES", week)
    first_id = db.query(Weekly).filter_by(semana_referencia=week).one().id

    monkeypatch.setattr(scheduler, "criar_weekly_com_rollover", real_create)
    now = datetime(2026, 10, 9, 12, tzinfo=FUSO_LLAB)
    result = scheduler.recuperar_execucoes_pendentes_sync(db, now)
    assert result["criacao_recuperada"] is True
    assert scheduler.foi_executado(db, "CRIAR_WEEKLIES", week)
    rows = db.query(Weekly).filter_by(semana_referencia=week).all()
    assert len(rows) == 2
    assert first_id in {w.id for w in rows}
    assert (
        scheduler.recuperar_execucoes_pendentes_sync(db, now)["criacao_recuperada"]
        is False
    )


@pytest.mark.parametrize("marco", [None, date(2026, 8, 28)])
def test_recupera_mais_de_oito_semanas_em_ordem_sem_pular_advertencias(
    recovery_db, monkeypatch, marco
):
    db = recovery_db
    monkeypatch.setattr(settings, "WEEKLY_MARCO_IMPLANTACAO", marco)
    member = _criar_membro(db, "Membro Ausente", "absent@test.com", "ABSENT")
    member.data_ingresso = date(2026, 8, 28)
    assoc = (
        db.query(SectorUser)
        .filter_by(usuario_id=member.id, setor_id=TestID.SETOR_TESTE)
        .one()
    )
    assoc.data_ingresso = date(2026, 8, 28)
    db.commit()
    scheduler.registrar_execucao_job(db, "VERIFICAR_AUSENCIAS", date(2026, 8, 31))
    now = datetime(2026, 11, 10, 1, 1, tzinfo=FUSO_LLAB)
    result = scheduler.recuperar_execucoes_pendentes_sync(db, now)
    expected = [str(date(2026, 9, 7) + timedelta(weeks=i)) for i in range(10)]
    assert result["ausencias_recuperadas"] == expected
    warnings = (
        db.query(WeeklyWarning)
        .filter_by(usuario_id=member.id)
        .order_by(WeeklyWarning.semana_referencia)
        .all()
    )
    assert [w.tipo for w in warnings[:3]] == [
        "1a_ADVERTENCIA",
        "2a_ADVERTENCIA",
        "DESLIGAMENTO",
    ]
    assert len(warnings) == 10
    assert (
        scheduler.recuperar_execucoes_pendentes_sync(db, now)["ausencias_recuperadas"]
        == []
    )
    assert db.query(WeeklyWarning).filter_by(usuario_id=member.id).count() == 10


def test_falha_no_historico_e_propagada_sem_marcar_sucesso(recovery_db, monkeypatch):
    def fail_commit(db):
        raise RuntimeError("Banco indisponível")

    monkeypatch.setattr(scheduler, "commit_changes", fail_commit)
    with pytest.raises(RuntimeError, match="Banco indisponível"):
        scheduler.registrar_execucao_job(
            recovery_db, "CRIAR_WEEKLIES", date(2026, 10, 5)
        )
    assert not scheduler.foi_executado(recovery_db, "CRIAR_WEEKLIES", date(2026, 10, 5))


def test_falha_interrompe_sequencia_e_retentativa_continua_da_pendencia(
    recovery_db, monkeypatch
):
    db = recovery_db
    monkeypatch.setattr(settings, "WEEKLY_MARCO_IMPLANTACAO", date(2026, 9, 7))
    original = scheduler.executar_verificacao_ausencias
    calls = []

    def fail_second(db, semana_referencia):
        calls.append(semana_referencia)
        if semana_referencia == date(2026, 9, 14):
            raise RuntimeError("Interrupção")
        return original(db, semana_referencia)

    monkeypatch.setattr(scheduler, "executar_verificacao_ausencias", fail_second)
    now = datetime(2026, 9, 29, 1, 1, tzinfo=FUSO_LLAB)
    with pytest.raises(RuntimeError, match="Interrupção"):
        scheduler.recuperar_execucoes_pendentes_sync(db, now)
    assert calls == [date(2026, 9, 7), date(2026, 9, 14)]
    monkeypatch.setattr(scheduler, "executar_verificacao_ausencias", original)
    result = scheduler.recuperar_execucoes_pendentes_sync(db, now)
    assert result["ausencias_recuperadas"] == ["2026-09-14", "2026-09-21", "2026-09-28"]
    assert (
        db.query(WeeklySchedulerExecution).filter_by(tipo="VERIFICAR_AUSENCIAS").count()
        == 4
    )
