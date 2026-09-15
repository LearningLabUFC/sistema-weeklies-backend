"""
Modelo ORM — Setor.

Representa a tabela 'setores' no banco de dados PostgreSQL.
Um setor agrupa membros e líderes dentro do projeto.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Sector(Base):
    """Modelo ORM para a tabela de setores do sistema."""

    __tablename__ = "setores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(100), unique=True, nullable=False, index=True)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    # relação 1:N com a tabela associativa
    usuarios = relationship("SectorUser", back_populates="setor")

    def __repr__(self) -> str:
        return f"<Sector {self.nome} (Ativo: {self.ativo})>"
