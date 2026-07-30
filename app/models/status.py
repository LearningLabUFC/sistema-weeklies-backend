"""
Modelo ORM — Status.

Representa a tabela 'status_usuarios' no banco de dados PostgreSQL.
Utilizada para controlar o fluxo de aprovação e deleção lógica.
"""

import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Status(Base):
    """Modelo ORM para os status de usuários."""

    __tablename__ = "status_usuarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(50), unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Status {self.nome}>"
