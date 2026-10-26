"""
Modelo ORM — TaskAssignment (Atribuição de Task).

Representa a tabela 'atribuicoes_task' no banco de dados PostgreSQL.
Registra o convite de atribuição de uma task a outro membro,
com ciclo de vida PENDENTE → ACEITA | RECUSADA.
Ao aceitar, o sistema clona a task para o membro convidado (origem_task_id).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class TaskAssignment(Base):
    """Modelo ORM para a tabela de atribuições/convites de tasks."""

    __tablename__ = "atribuicoes_task"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    solicitante_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    atribuido_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    status = Column(
        String(20), nullable=False, default="PENDENTE",
        comment="PENDENTE | ACEITA | RECUSADA | EXPIRADA",
    )
    criado_em = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    respondido_em = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    task = relationship("Task", back_populates="atribuicoes")
    solicitante = relationship("User", foreign_keys=[solicitante_id])
    atribuido = relationship("User", foreign_keys=[atribuido_id])

    def __repr__(self) -> str:
        return f"<TaskAssignment task={self.task_id} de={self.solicitante_id} para={self.atribuido_id} status={self.status}>"
