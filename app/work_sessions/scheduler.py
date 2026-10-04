import asyncio
import logging

from app.database import SessionLocal
from app.work_sessions.service import svc_process_expired_sessions

logger = logging.getLogger("uvicorn.error")


async def work_sessions_scheduler() -> None:
    while True:
        db = SessionLocal()

        try:
            svc_process_expired_sessions(db)
        except Exception:
            db.rollback()
            logger.exception(
                "Erro ao processar sessões de trabalho expiradas."
            )
        finally:
            db.close()

        await asyncio.sleep(60)