"""
Modelo ORM — WeeklyWarning (Advertência de Weekly).

Representa a tabela 'advertencias_weekly' no banco de dados PostgreSQL.
Registra advertências automáticas geradas pelo sistema quando um membro
acumula semanas consecutivas sem enviar sua weekly.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class WeeklyWarning(Base):
    """Modelo ORM para a tabela de advertências de weeklies."""

    __tablename__ = "advertencias_weekly"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    setor_id = Column(UUID(as_uuid=True), ForeignKey("setores.id"), nullable=False)
    tipo = Column(String(20), nullable=False)
    semana_referencia = Column(Date, nullable=False)
    semanas_ausentes = Column(Integer, nullable=False)
    criado_em = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    # Relationships
    usuario = relationship("User")
    setor = relationship("Sector")

    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            "setor_id",
            "semana_referencia",
            name="uq_warning_usuario_setor_semana",
        ),
    )

    def __repr__(self) -> str:
        return f"<WeeklyWarning user={self.usuario_id} tipo={self.tipo} semana={self.semana_referencia}>"
