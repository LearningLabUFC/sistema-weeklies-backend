"""
Modelo ORM — Task.

Representa a tabela 'tasks' no banco de dados PostgreSQL.
Cada task é uma meta/tarefa atribuída a um membro dentro de um setor,
com ciclo de vida independente (PENDENTE → CONCLUIDA | EM_AUDITORIA | REMOVIDA_PELO_LIDER).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Task(Base):
    """Modelo ORM para a tabela de tasks (metas semanais)."""

    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    setor_id = Column(UUID(as_uuid=True), ForeignKey("setores.id"), nullable=False)
    origem_task_id = Column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True,
        comment="Rastreabilidade: referência à task original quando clonada por atribuição/convite",
    )
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="PENDENTE")
    prazo_conclusao = Column(Date, nullable=True)
    removida_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    entrada_auditoria_em = Column(
        DateTime(timezone=True), nullable=True,
        comment="Registra quando a task entrou em EM_AUDITORIA (independente de atualizado_em)",
    )
    criado_em = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    atualizado_em = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("usuario_id", "origem_task_id", name="uq_tasks_usuario_origem"),
    )

    # Relationships
    usuario = relationship("User", foreign_keys=[usuario_id])
    setor = relationship("Sector")
    removedor = relationship("User", foreign_keys=[removida_por])
    origem_task = relationship("Task", remote_side=[id])
    weekly_tasks = relationship("WeeklyTask", back_populates="task")
    atribuicoes = relationship("TaskAssignment", back_populates="task")

    def __repr__(self) -> str:
        return f"<Task {self.titulo!r} user={self.usuario_id} status={self.status}>"
