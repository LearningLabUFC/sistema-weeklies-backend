"""Módulo de Jobs do APScheduler para Weeklies (Fase 6).

Jobs Agendados:
1. `job_criar_weeklies`: Executado toda sexta-feira às 00:00 (America/Fortaleza).
   - Cria weeklies em lote em status RASCUNHO para todos os membros ativos em setores ativos.
   - Aplica o rollover automático de tasks pendentes (origem='HERDADA').
   - Idempotente: não recria weeklies que já existam para a mesma semana de referência.

2. `job_verificar_ausencias`: Executado toda terça-feira às 01:00 (America/Fortaleza).
   - Detecta membros que não enviaram a weekly da janela recém-fechada (segunda-feira anterior).
   - Registra logs detalhados e prepara base para advertências (Fase 7) e auditoria (Fase 8).
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, engine
from app.models.weekly_scheduler_execution import WeeklySchedulerExecution
from app.weeklies.repository import (
    commit_changes,
    find_active_sector_members,
    find_weekly_by_user_sector_semana,
)
from app.weeklies.service import (
    calcular_inicio_obrigacao_setor,
    calcular_primeira_semana_obrigatoria,
    criar_weekly_com_rollover,
    svc_processar_advertencias_ausencias,
    svc_processar_auditoria_tasks,
    svc_processar_expiracao_weeklies,
)
from app.weeklies.timezone_utils import (
    dentro_da_janela,
    get_now_fortaleza,
    obter_semana_referencia,
)

logger = logging.getLogger("uvicorn.error")


def foi_executado(db: Session, tipo: str, semana_referencia: date) -> bool:
    """Verifica se determinado tipo de job já foi executado para a semana de referência."""
    return (
        db.query(WeeklySchedulerExecution)
        .filter(
            WeeklySchedulerExecution.tipo == tipo,
            WeeklySchedulerExecution.semana_referencia == semana_referencia,
        )
        .first()
        is not None
    )


def registrar_execucao_job(db: Session, tipo: str, semana_referencia: date) -> None:
    """Registra no banco de dados que um job do scheduler foi executado com sucesso."""
    try:
        if not foi_executado(db, tipo, semana_referencia):
            execucao = WeeklySchedulerExecution(
                tipo=tipo,
                semana_referencia=semana_referencia,
                executado_em=datetime.now(timezone.utc),
            )
            db.add(execucao)
            commit_changes(db)
    except Exception:
        db.rollback()
        logger.exception(
            "Erro ao registrar execução do scheduler para %s %s", tipo, semana_referencia
        )
        raise


def obter_ultima_semana_fechada_para_ausencias(momento: datetime) -> date:
    """Calcula a data da segunda-feira mais recente cuja verificação de ausências
    já deveria ter ocorrido (terça-feira às 01:00 ou posterior).
    """
    momento = momento.astimezone(ZoneInfo(settings.WEEKLY_TIMEZONE))
    hoje = momento.date()
    dia_semana = hoje.weekday()
    if dia_semana == 1 and momento.hour < 1:
        # Terça antes das 01:00: o job da semana que fechou ontem ainda vai rodar às 01:00
        return hoje - timedelta(days=8)
    elif dia_semana == 0:
        # Segunda-feira: a janela de hoje ainda está aberta; a última fechada é a da semana anterior
        return hoje - timedelta(days=7)
    else:
        # Terça após 01:00 até Domingo: a última segunda fechada foi a segunda desta semana
        return hoje - timedelta(days=dia_semana)


def executar_criacao_weeklies_lote(
    db: Session, semana_referencia: date | None = None
) -> dict[str, Any]:
    """Executa a criação em lote de weeklies com rollover de tarefas pendentes.

    Função síncrona projetada para ser executada em thread separada pelo scheduler
    ou chamada diretamente em scripts/testes.
    """
    if semana_referencia is None:
        semana_referencia = obter_semana_referencia()

    # Expira weeklies não finalizadas de ciclos anteriores antes de criar o novo lote
    res_expiracao = svc_processar_expiracao_weeklies(db, semana_referencia)
    logger.info(
        "🧹 [CRON] Varredura de expiração executada: %d weeklies expiradas.",
        res_expiracao.get("total_expiradas", 0),
    )

    membros_setores = find_active_sector_members(db)
    criadas = 0
    ignoradas = 0
    erros = 0

    logger.info(
        "🚀 [CRON] Iniciando criação em lote de weeklies para a semana %s (%d membros ativos encontrados)...",
        semana_referencia,
        len(membros_setores),
    )

    for assoc in membros_setores:
        try:
            existente = find_weekly_by_user_sector_semana(
                db, assoc.usuario_id, assoc.setor_id, semana_referencia
            )
            if existente:
                ignoradas += 1
                continue

            criar_weekly_com_rollover(
                db, assoc.usuario_id, assoc.setor_id, semana_referencia
            )
            criadas += 1
        except Exception:
            db.rollback()
            erros += 1
            logger.exception(
                "❌ [CRON] Erro ao criar weekly para membro %s no setor %s",
                assoc.usuario_id,
                assoc.setor_id,
            )

    logger.info(
        "✅ [CRON] Criação em lote finalizada: %d criadas, %d já existiam, %d erros.",
        criadas,
        ignoradas,
        erros,
    )
    if erros == 0:
        registrar_execucao_job(db, "CRIAR_WEEKLIES", semana_referencia)
    return {
        "semana_referencia": str(semana_referencia),
        "total_membros": len(membros_setores),
        "criadas": criadas,
        "ignoradas": ignoradas,
        "erros": erros,
        "expiracao": res_expiracao,
    }


def executar_verificacao_ausencias(
    db: Session, semana_referencia: date | None = None
) -> dict[str, Any]:
    """Identifica membros que não enviaram relatório semanal para a semana de referência
    e gera as advertências automáticas correspondentes (Fase 7), além de executar a auditoria
    e escalonamento de tarefas vencidas (Fase 8).
    """
    if semana_referencia is None:
        semana_referencia = obter_semana_referencia()

    res_adv = svc_processar_advertencias_ausencias(db, semana_referencia)
    res_auditoria = svc_processar_auditoria_tasks(db)
    resultado = dict(res_adv)
    resultado["auditoria"] = res_auditoria
    registrar_execucao_job(db, "VERIFICAR_AUSENCIAS", semana_referencia)
    return resultado



LOCK_ID_CRIAR_WEEKLIES = 771001
LOCK_ID_VERIFICAR_AUSENCIAS = 771002


def _executar_com_sessao(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Executa a função síncrona encapsulando a criação e o descarte da sessão de banco."""
    with SessionLocal() as db:
        return func(db, *args, **kwargs)


def _executar_com_advisory_lock(
    lock_id: int, func: Any, *args: Any, **kwargs: Any
) -> Any:
    """Executa a função síncrona coordenando a execução entre múltiplos workers/instâncias
    via PostgreSQL Advisory Lock.
    Reserva uma conexão dedicada exclusiva do engine durante toda a duração do lock para
    garantir que o acquire e o unlock ocorram rigorosamente na mesma conexão física.
    """
    is_postgres = engine.dialect.name == "postgresql"
    if not is_postgres:
        with SessionLocal() as db:
            return func(db, *args, **kwargs)

    # Reserva uma conexão dedicada diretamente do engine para a duração do lock
    with engine.connect() as lock_conn:
        adquiriu = lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
        ).scalar()

        if not adquiriu:
            logger.warning(
                "⏭️ [CRON] Advisory lock %d já adquirido por outra réplica/instância. "
                "Ignorando execução concorrente de '%s'.",
                lock_id,
                func.__name__,
            )
            return {
                "executado": False,
                "motivo": "lock_concorrente_adquirido_por_outra_instancia",
            }

        try:
            with SessionLocal() as db:
                return func(db, *args, **kwargs)
        finally:
            try:
                lock_conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id}
                )
            except Exception:
                logger.exception("Erro ao liberar advisory lock %d.", lock_id)


async def job_criar_weeklies() -> Any:
    """Job disparado na sexta-feira às 00:00 (America/Fortaleza)."""
    return await asyncio.to_thread(
        _executar_com_advisory_lock, LOCK_ID_CRIAR_WEEKLIES, executar_criacao_weeklies_lote
    )


async def job_verificar_ausencias() -> Any:
    """Job disparado na terça-feira às 01:00 (America/Fortaleza)."""
    # Processa primeiro as referências antigas para preservar a sequência de advertências.
    return await recuperar_execucoes_pendentes()


def registrar_jobs_weeklies(scheduler: AsyncIOScheduler) -> None:
    """Registra os jobs recorrentes de weeklies no agendador."""
    fuso = ZoneInfo(settings.WEEKLY_TIMEZONE)

    scheduler.add_job(
        job_criar_weeklies,
        trigger="cron",
        day_of_week="fri",
        hour=0,
        minute=0,
        timezone=fuso,
        id="criar_weeklies",
        name="Criação em lote de Weeklies e Rollover de Tasks",
        replace_existing=True,
    )

    scheduler.add_job(
        job_verificar_ausencias,
        trigger="cron",
        day_of_week="tue",
        hour=1,
        minute=0,
        timezone=fuso,
        id="verificar_ausencias",
        name="Verificação pós-fechamento de ausências de envio de weeklies",
        replace_existing=True,
    )

    scheduler.add_job(
        recuperar_execucoes_pendentes,
        trigger="interval",
        minutes=5,
        next_run_time=get_now_fortaleza(),
        id="recuperar_weeklies",
        name="Recuperação de execuções pendentes de Weeklies",
        replace_existing=True,
    )


def recuperar_execucoes_pendentes_sync(
    db: Session | None = None,
    momento: datetime | None = None,
) -> dict[str, Any]:
    """Varre e recupera execuções de jobs de weeklies que foram perdidas durante paradas do servidor.
    Garante idempotência através do registro na tabela `weekly_scheduler_execucoes`
    e coordenação entre réplicas via advisory locks.
    """
    if momento is None:
        momento = get_now_fortaleza()

    def _recuperar_ausencias(session: Session) -> list[str]:
        ultima_semana = obter_ultima_semana_fechada_para_ausencias(momento)
        # Reusa a regra de início da obrigação dos membros ativos
        inicios = [
            calcular_primeira_semana_obrigatoria(calcular_inicio_obrigacao_setor(assoc))
            for assoc in find_active_sector_members(session)
        ]
        ultimo_registro = session.query(
            func.max(WeeklySchedulerExecution.semana_referencia)
        ).filter(WeeklySchedulerExecution.tipo == "VERIFICAR_AUSENCIAS").scalar()

        marco = (
            calcular_primeira_semana_obrigatoria(settings.WEEKLY_MARCO_IMPLANTACAO)
            if settings.WEEKLY_MARCO_IMPLANTACAO
            else None
        )

        if ultimo_registro:
            semana = ultimo_registro + timedelta(days=7)
            if marco:
                semana = max(semana, marco)
        elif marco:
            semana = marco
        elif inicios:
            semana = max(min(inicios), ultima_semana - timedelta(weeks=12))
        else:
            semana = ultima_semana

        recuperadas = []
        while semana <= ultima_semana:
            # A verificação e o processamento ocorrem sob o mesmo advisory lock.
            if not foi_executado(session, "VERIFICAR_AUSENCIAS", semana):
                executar_verificacao_ausencias(session, semana_referencia=semana)
                recuperadas.append(str(semana))
            semana += timedelta(days=7)
        return recuperadas

    def _recuperar_criacao(session: Session) -> bool:
        if not dentro_da_janela(momento):
            return False
        semana = obter_semana_referencia(momento)
        if foi_executado(session, "CRIAR_WEEKLIES", semana):
            return False
        resultado = executar_criacao_weeklies_lote(session, semana_referencia=semana)
        return resultado["erros"] == 0

    if db is not None:
        ausencias = _recuperar_ausencias(db)
        criacao = _recuperar_criacao(db)
    else:
        ausencias = _executar_com_advisory_lock(
            LOCK_ID_VERIFICAR_AUSENCIAS, _recuperar_ausencias
        )
        criacao = _executar_com_advisory_lock(
            LOCK_ID_CRIAR_WEEKLIES, _recuperar_criacao
        )

    return {
        "ausencias_recuperadas": ausencias if isinstance(ausencias, list) else [],
        "criacao_recuperada": criacao is True,
    }


async def recuperar_execucoes_pendentes(
    momento: datetime | None = None,
) -> dict[str, Any]:
    """Versão assíncrona para ser chamada na inicialização do servidor ou via background tasks."""
    return await asyncio.to_thread(recuperar_execucoes_pendentes_sync, None, momento)
