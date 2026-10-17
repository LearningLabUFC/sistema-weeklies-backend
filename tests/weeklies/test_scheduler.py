"""Testes para a Fase 6: Automação e Cron Jobs (APScheduler).

Cenários cobertos:
1. Configuração e registro dos jobs no APScheduler (criar_weeklies na sexta 00h e verificar_ausencias na terça 01h).
2. Execução em lote da criação de weeklies na sexta-feira com rollover automático para todos os membros ativos.
3. Idempotência: reexecução no mesmo período não gera duplicatas nem erros.
4. Isolamento: membros inativos, setores inativos e papéis que não são membros não recebem weekly pré-criada.
5. Verificação de ausências na terça-feira: detecção correta de weeklies em RASCUNHO e não-criadas.
6. Ciclo de vida do scheduler (iniciar / encerrar) respeitando a flag ENABLE_SCHEDULER.
"""

from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.config import settings
from app.core.constants import RoleID, StatusID, TestID
from app.core.scheduler import encerrar_scheduler, get_scheduler, iniciar_scheduler
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_scheduler_execution import WeeklySchedulerExecution
from app.weeklies.scheduler import (
    executar_criacao_weeklies_lote,
    executar_verificacao_ausencias,
    foi_executado,
    recuperar_execucoes_pendentes_sync,
    registrar_jobs_weeklies,
)

REFERENCE_FRIDAY = date(2026, 10, 2)  # Sexta-feira
NEXT_MONDAY = date(2026, 10, 5)       # Segunda-feira seguinte (semana_referencia)


def _criar_membro(
    db_session,
    nome: str,
    email: str,
    matricula: str,
    papel: str = "membro",
    status_id=StatusID.ATIVO,
    setor_id=TestID.SETOR_TESTE,
) -> User:
    user = User(
        nome_completo=nome,
        email=email,
        senha_hash="hash",
        matricula=matricula,
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=status_id,
        global_role=RoleID.USUARIO,
    )
    db_session.add(user)
    db_session.flush()

    assoc = SectorUser(
        usuario_id=user.id,
        setor_id=setor_id,
        papel=papel,
        data_ingresso=date(2026, 1, 1),
    )
    db_session.add(assoc)
    db_session.commit()
    return user


def test_registro_jobs_apscheduler():
    """Valida que os jobs recorrentes de weeklies são configurados com triggers corretos."""
    scheduler = get_scheduler()
    registrar_jobs_weeklies(scheduler)

    job_criar = scheduler.get_job("criar_weeklies")
    assert job_criar is not None
    assert str(job_criar.trigger) == "cron[day_of_week='fri', hour='0', minute='0']"

    job_ausencias = scheduler.get_job("verificar_ausencias")
    assert job_ausencias is not None
    assert str(job_ausencias.trigger) == "cron[day_of_week='tue', hour='1', minute='0']"


def test_criacao_em_lote_com_rollover(db_session):
    """Testa a criação automática de weeklies na sexta com herança de tasks pendentes."""
    m1 = _criar_membro(db_session, "Membro Cron 1", f"m1_{uuid4().hex[:6]}@test.com", f"M1_{uuid4().hex[:5]}")
    m2 = _criar_membro(db_session, "Membro Cron 2", f"m2_{uuid4().hex[:6]}@test.com", f"M2_{uuid4().hex[:5]}")

    # Tasks pendentes para m1
    t1 = Task(usuario_id=m1.id, setor_id=TestID.SETOR_TESTE, titulo="Task Pendente M1", status="PENDENTE")
    # Task concluída para m1 (não deve herdar)
    t2 = Task(usuario_id=m1.id, setor_id=TestID.SETOR_TESTE, titulo="Task Concluída M1", status="CONCLUIDA")
    # Task pendente para m2
    t3 = Task(usuario_id=m2.id, setor_id=TestID.SETOR_TESTE, titulo="Task Pendente M2", status="PENDENTE")

    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # Executa o job de sexta
    res = executar_criacao_weeklies_lote(db_session, semana_referencia=NEXT_MONDAY)

    assert res["criadas"] >= 2
    assert res["erros"] == 0

    # Valida que as weeklies foram criadas com status RASCUNHO
    w1 = db_session.query(Weekly).filter(
        Weekly.usuario_id == m1.id,
        Weekly.setor_id == TestID.SETOR_TESTE,
        Weekly.semana_referencia == NEXT_MONDAY,
    ).first()
    assert w1 is not None
    assert w1.status == "RASCUNHO"
    assert len(w1.weekly_tasks) == 1
    assert w1.weekly_tasks[0].task_id == t1.id
    assert w1.weekly_tasks[0].origem == "HERDADA"
    assert not w1.weekly_tasks[0].concluida

    w2 = db_session.query(Weekly).filter(
        Weekly.usuario_id == m2.id,
        Weekly.setor_id == TestID.SETOR_TESTE,
        Weekly.semana_referencia == NEXT_MONDAY,
    ).first()
    assert w2 is not None
    assert len(w2.weekly_tasks) == 1
    assert w2.weekly_tasks[0].task_id == t3.id


def test_criacao_em_lote_idempotente(db_session):
    """Executar a criação em lote duas vezes para a mesma semana não duplica registros."""
    m = _criar_membro(db_session, "Membro Idempotente", f"m_{uuid4().hex[:6]}@test.com", f"M_{uuid4().hex[:5]}")
    t = Task(usuario_id=m.id, setor_id=TestID.SETOR_TESTE, titulo="Task Única", status="PENDENTE")
    db_session.add(t)
    db_session.commit()

    # Primeira execução: cria
    res1 = executar_criacao_weeklies_lote(db_session, semana_referencia=NEXT_MONDAY)
    assert res1["criadas"] >= 1

    # Segunda execução: ignora já existentes
    res2 = executar_criacao_weeklies_lote(db_session, semana_referencia=NEXT_MONDAY)
    assert res2["criadas"] == 0
    assert res2["ignoradas"] >= 1
    assert res2["erros"] == 0


def test_criacao_em_lote_ignora_inativos_e_cria_para_lideres(db_session):
    """Usuários inativos e setores inativos não recebem weeklies, mas líderes ativos recebem."""
    # Usuário inativo
    _m_inativo = _criar_membro(
        db_session,
        "Inativo",
        f"inativo_{uuid4().hex[:6]}@test.com",
        f"IN_{uuid4().hex[:5]}",
        status_id=StatusID.INATIVO,
    )

    # Setor inativo
    setor_inativo = Sector(id=uuid4(), nome=f"Setor Inativo {uuid4().hex[:4]}", ativo=False)
    db_session.add(setor_inativo)
    db_session.flush()
    _m_setor_inativo = _criar_membro(
        db_session,
        "Membro Setor Inativo",
        f"msi_{uuid4().hex[:6]}@test.com",
        f"MSI_{uuid4().hex[:5]}",
        setor_id=setor_inativo.id,
    )

    # Líder ativo (no modelo híbrido, líderes também entregam weekly)
    _lider = _criar_membro(
        db_session,
        "Lider Setor",
        f"lider_{uuid4().hex[:6]}@test.com",
        f"LID_{uuid4().hex[:5]}",
        papel="lider",
    )

    res = executar_criacao_weeklies_lote(db_session, semana_referencia=NEXT_MONDAY)
    assert res["criadas"] == 1

    # Nenhuma weekly para inativo ou setor inativo; weekly criada para o líder ativo
    w_inativo = db_session.query(Weekly).filter(Weekly.usuario_id == _m_inativo.id).first()
    w_setor_inativo = db_session.query(Weekly).filter(Weekly.usuario_id == _m_setor_inativo.id).first()
    w_lider = db_session.query(Weekly).filter(Weekly.usuario_id == _lider.id).first()

    assert w_inativo is None
    assert w_setor_inativo is None
    assert w_lider is not None


def test_verificacao_ausencias_terca(db_session):
    """Testa a detecção de ausências pós-fechamento da janela."""
    m_enviado = _criar_membro(db_session, "Membro Enviou", f"env_{uuid4().hex[:6]}@test.com", f"ENV_{uuid4().hex[:5]}")
    m_rascunho = _criar_membro(db_session, "Membro Rascunho", f"rasc_{uuid4().hex[:6]}@test.com", f"RASC_{uuid4().hex[:5]}")
    m_nada = _criar_membro(db_session, "Membro Sem Weekly", f"nada_{uuid4().hex[:6]}@test.com", f"NADA_{uuid4().hex[:5]}")

    sem_ref = NEXT_MONDAY

    # Weekly enviada
    w_env = Weekly(usuario_id=m_enviado.id, setor_id=TestID.SETOR_TESTE, semana_referencia=sem_ref, status="ENVIADA")
    # Weekly em rascunho (não enviada no prazo)
    w_rasc = Weekly(usuario_id=m_rascunho.id, setor_id=TestID.SETOR_TESTE, semana_referencia=sem_ref, status="RASCUNHO")

    db_session.add_all([w_env, w_rasc])
    db_session.commit()

    res = executar_verificacao_ausencias(db_session, semana_referencia=sem_ref)

    assert res["enviadas"] >= 1
    assert res["ausencias"] >= 2

    # Verifica se os IDs constam na lista de ausentes
    usuarios_ausentes = [d["usuario_id"] for d in res["detalhes_ausentes"]]
    assert str(m_rascunho.id) in usuarios_ausentes
    assert str(m_nada.id) in usuarios_ausentes
    assert str(m_enviado.id) not in usuarios_ausentes


def test_lifecycle_scheduler(monkeypatch):
    """Testa a inicialização e o encerramento do agendador."""
    encerrar_scheduler()

    # Quando desabilitado
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
    iniciar_scheduler()
    assert not get_scheduler().running

    # Quando habilitado
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", True)
    iniciar_scheduler()
    assert get_scheduler().running

    encerrar_scheduler()
    assert not get_scheduler().running


def test_execucoes_registram_historico_idempotente(db_session):
    """Execução dos jobs deve registrar histórico e ser idempotente."""
    sem_ref = date(2026, 11, 2)

    # Inicialmente não foi executado
    assert not foi_executado(db_session, "CRIAR_WEEKLIES", sem_ref)
    assert not foi_executado(db_session, "VERIFICAR_AUSENCIAS", sem_ref)

    # Executa criação
    executar_criacao_weeklies_lote(db_session, semana_referencia=sem_ref)
    assert foi_executado(db_session, "CRIAR_WEEKLIES", sem_ref)

    # Executa verificação de ausências
    executar_verificacao_ausencias(db_session, semana_referencia=sem_ref)
    assert foi_executado(db_session, "VERIFICAR_AUSENCIAS", sem_ref)

    # Reexecutar não cria duplicatas na tabela de execuções
    executar_criacao_weeklies_lote(db_session, semana_referencia=sem_ref)
    qtd_criar = (
        db_session.query(WeeklySchedulerExecution)
        .filter_by(tipo="CRIAR_WEEKLIES", semana_referencia=sem_ref)
        .count()
    )
    assert qtd_criar == 1


def test_recuperacao_execucoes_perdidas_apos_parada_do_servidor(db_session):
    """Se o servidor iniciar na terça às 01:01, a verificação de ausências perdida
    da semana recém-fechada deve ser detectada e recuperada de forma idempotente.
    """
    # Terça-feira, 13/10/2026 às 01:01 (horário de Fortaleza)
    # A semana de referência fechada na segunda anterior é 12/10/2026
    momento_terca_0101 = datetime(2026, 10, 13, 1, 1, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    sem_fechada = date(2026, 10, 12)

    # Garante que a execução da semana fechada ainda não consta no banco
    assert not foi_executado(db_session, "VERIFICAR_AUSENCIAS", sem_fechada)

    # Executa a rotina de recuperação simulando a inicialização do servidor
    resultado = recuperar_execucoes_pendentes_sync(db=db_session, momento=momento_terca_0101)

    assert str(sem_fechada) in resultado["ausencias_recuperadas"]
    assert foi_executado(db_session, "VERIFICAR_AUSENCIAS", sem_fechada)

    # Segunda chamada imediata (idempotente): não deve reexecutar
    resultado_segunda_vez = recuperar_execucoes_pendentes_sync(db=db_session, momento=momento_terca_0101)
    assert len(resultado_segunda_vez["ausencias_recuperadas"]) == 0

