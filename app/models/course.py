"""
Modelo ORM — Curso.

Representa a tabela 'cursos' no banco de dados PostgreSQL.
Um curso pode ter varios usuarios associados.
"""

import uuid
from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Course(Base):
    """Modelo ORM para a tabela de cursos do sistema."""

    __tablename__ = "cursos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(100), nullable=False)
    ativo = Column(Boolean, nullable=False, default=True)

    # relacao 1 para N
    usuarios = relationship("User", back_populates="curso")

    def __repr__(self) -> str:
        return f"<Course {self.nome} (Ativo: {self.ativo})>"
