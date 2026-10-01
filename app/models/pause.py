"""
Modelo ORM — Pausa.

Registra os intervalos de uma sessão de trabalho.
O fim permanece nulo enquanto a pausa estiver aberta.
"""

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Pause(Base):
    __tablename__ = "pausas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sessao_trabalho_id = Column(UUID(as_uuid=True), ForeignKey("sessoes_trabalho.id"), nullable=False, index = True)
    inicio = Column(DateTime, nullable=False)
    fim = Column(DateTime, nullable=True)

    # Relacionamentos
    sessao_trabalho = relationship("WorkSession", back_populates="pausas")

    __table_args__ = (
        Index(
            "uq_sessao_pausa_aberta",
            "sessao_trabalho_id",
            unique=True,
            postgresql_where=text("fim IS NULL")
        ),
        CheckConstraint(
            "fim IS NULL OR fim >= inicio",
            name="ck_pausa_fim_valido"
        ),
    )

    def __repr__(self) -> str:
        return f"<Pause {self.id} - {self.inicio} - {self.fim}>"