"""
Modelo ORM — Usuário.

Representa a tabela 'usuarios' no banco de dados PostgreSQL.
Campos baseados no schema Pydantic UsuarioCompleto (app/schemas.py).
"""

import uuid

from sqlalchemy import Column, Date, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class User(Base):
    """Modelo ORM para a tabela de usuários do sistema."""

    __tablename__ = "usuarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome_completo = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    senha_hash = Column(String(255), nullable=False)
    matricula = Column(String(20), unique=True, nullable=False, index=True)
    data_nascimento = Column(Date, nullable=False)
    data_ingresso = Column(Date, nullable=False)
    meta_horas_semanais = Column(Integer, nullable=False, default=12)
    foto_perfil = Column(String(500), nullable=True, default="avatar_padrao.png")

    # UUIDs referenciais — serão convertidos em ForeignKey
    # quando as tabelas de cursos, status e roles forem criadas.
    curso_id = Column(UUID(as_uuid=True), nullable=False)
    status_id = Column(UUID(as_uuid=True), nullable=True)
    global_role = Column(UUID(as_uuid=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User {self.nome_completo} ({self.email})>"
