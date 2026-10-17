"""
Modelo ORM — WeeklyTask (tabela associativa).

Representa a tabela 'weekly_tasks' no banco de dados PostgreSQL.
Liga uma Task a uma Weekly específica, registrando se foi concluída,
se há impedimento, a posição no card e a origem (NOVA ou HERDADA).
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class WeeklyTask(Base):
    """Modelo ORM para a tabela associativa weekly ↔ task."""

    __tablename__ = "weekly_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    weekly_id = Column(UUID(as_uuid=True), ForeignKey("weeklies.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    concluida = Column(Boolean, nullable=False, default=False)
    impedimento = Column(Text, nullable=True)
    posicao = Column(Integer, nullable=False, default=0)
    origem = Column(String(10), nullable=False, default="NOVA")

    # Campos de Snapshot Histórico (congelados na submissão/aprovação da weekly)
    snapshot_titulo = Column(String(255), nullable=True)
    snapshot_descricao = Column(Text, nullable=True)
    snapshot_prazo_conclusao = Column(Date, nullable=True)

    # Relationships
    weekly = relationship("Weekly", back_populates="weekly_tasks")
    task = relationship("Task", back_populates="weekly_tasks")

    __table_args__ = (
        UniqueConstraint("weekly_id", "task_id", name="uq_weekly_task"),
    )

    def __repr__(self) -> str:
        return f"<WeeklyTask weekly={self.weekly_id} task={self.task_id} concluida={self.concluida}>"
