"""Módulo APScheduler — Configuração central e ciclo de vida do agendador."""

import asyncio
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger("uvicorn.error")

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Retorna a instância global do agendador configurado com o timezone oficial."""
    global _scheduler
    if _scheduler is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        _scheduler = AsyncIOScheduler(
            timezone=ZoneInfo(settings.WEEKLY_TIMEZONE),
            event_loop=loop,
            job_defaults={
                "misfire_grace_time": 3600 * 24 * 7,
                "coalesce": True,
                "max_instances": 1,
            },
        )
    return _scheduler


def iniciar_scheduler() -> None:
    """Inicia o APScheduler caso esteja habilitado nas configurações."""
    if not settings.ENABLE_SCHEDULER:
        logger.info("⏸️ APScheduler desabilitado via configuração.")
        return

    scheduler = get_scheduler()
    if not scheduler.running:
        from app.weeklies.scheduler import registrar_jobs_weeklies

        registrar_jobs_weeklies(scheduler)
        scheduler.start()
        logger.info(
            "⏱️ APScheduler iniciado com sucesso (timezone: %s).",
            settings.WEEKLY_TIMEZONE,
        )


def encerrar_scheduler() -> None:
    """Encerra o APScheduler caso esteja em execução."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("🔌 APScheduler encerrado.")
        _scheduler = None
