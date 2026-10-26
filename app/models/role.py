"""
Modelo ORM — Cargo (Role).

Representa a tabela 'cargos' no banco de dados PostgreSQL.
Utilizada para o Controle de Acesso Baseado em Papéis (RBAC).
"""

import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Role(Base):
    """Modelo ORM para os cargos de usuários no sistema."""

    __tablename__ = "cargos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(50), unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Role {self.nome}>"
