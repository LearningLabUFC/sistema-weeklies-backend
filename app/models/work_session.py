"""
Modelo ORM — Sessão de Trabalho.

Registra entrada, saída e expiração de uma sessão,
vinculada a um usuário e a um setor.
"""

import enum
import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class WorkSessionStatus(str, enum.Enum):
    ATIVA = "ATIVA"
    EM_PAUSA = "EM_PAUSA"
    FINALIZADA = "FINALIZADA"
    EXPIRADA_SISTEMA = "EXPIRADA_SISTEMA"

class MotivoEncerramento(str, enum.Enum):
    MANUAL = "MANUAL"
    LIMITE_ATINGIDO = "LIMITE_ATINGIDO"


class WorkSession(Base):
    """Modelo ORM para a tabela de sessões de trabalho do sistema."""

    __tablename__ = "sessoes_trabalho"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index = True)
    setor_id = Column(UUID(as_uuid=True), ForeignKey("setores.id"), nullable=False, index = True)
    entrada = Column(DateTime(timezone=True), nullable=False)
    saida = Column(DateTime(timezone=True), nullable=True)
    expiracao = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(WorkSessionStatus), nullable=False, default=WorkSessionStatus.ATIVA)
    motivo_encerramento = Column(Enum(MotivoEncerramento), nullable=True)

    # Relacionamentos
    usuario = relationship("User", back_populates="sessao_trabalho")
    setor = relationship("Sector", back_populates="sessao_trabalho")
    pausas = relationship("Pause", back_populates="sessao_trabalho")

    __table_args__ = (
        Index(
            "uq_usuario_sessao_aberta",
            "usuario_id",
            unique=True,
            postgresql_where=text("saida IS NULL")
        ),
        CheckConstraint(
            "saida IS NULL OR saida >= entrada",
            name="ck_sessao_saida_valida"
        ),
    )

    def __repr__(self) -> str:
        return f"<WorkSession {self.id} - {self.usuario_id} - {self.setor_id}>"

