"""
Modelo ORM — WeeklySchedulerExecution.

Registra o histórico de execuções dos jobs periódicos do agendador (criação em lote e verificação de ausências),
permitindo recuperação automática de execuções perdidas durante paradas/reinicializações do servidor.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class WeeklySchedulerExecution(Base):
    """Registra execuções concluídas de jobs por semana de referência para garantir idempotência e catch-up."""

    __tablename__ = "weekly_scheduler_execucoes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(String(50), nullable=False, index=True)  # "CRIAR_WEEKLIES" | "VERIFICAR_AUSENCIAS"
    semana_referencia = Column(Date, nullable=False, index=True)
    executado_em = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "tipo",
            "semana_referencia",
            name="uq_scheduler_tipo_semana",
        ),
    )

    def __repr__(self) -> str:
        return f"<WeeklySchedulerExecution tipo={self.tipo} semana={self.semana_referencia}>"
