"""
Modelo ORM — Weekly.

Representa a tabela 'weeklies' no banco de dados PostgreSQL.
Cada registro é o relatório semanal de um membro em um setor específico.
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


class Weekly(Base):
    """Modelo ORM para a tabela de weeklies (relatórios semanais)."""

    __tablename__ = "weeklies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    setor_id = Column(UUID(as_uuid=True), ForeignKey("setores.id"), nullable=False)
    semana_referencia = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="RASCUNHO")
    enviada_em = Column(DateTime(timezone=True), nullable=True)
    avaliada_em = Column(DateTime(timezone=True), nullable=True)
    avaliada_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    observacao_lider = Column(Text, nullable=True)
    motivo_expiracao = Column(String(50), nullable=True)
    detalhe_expiracao = Column(Text, nullable=True)
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

    # Relationships
    usuario = relationship("User", foreign_keys=[usuario_id])
    setor = relationship("Sector")
    avaliador = relationship("User", foreign_keys=[avaliada_por])
    weekly_tasks = relationship("WeeklyTask", back_populates="weekly", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("usuario_id", "setor_id", "semana_referencia", name="uq_weekly_usuario_setor_semana"),
    )

    def __repr__(self) -> str:
        return f"<Weekly user={self.usuario_id} setor={self.setor_id} semana={self.semana_referencia} status={self.status}>"
