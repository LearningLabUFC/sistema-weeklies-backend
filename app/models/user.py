"""
Modelo ORM — Usuário.

Representa a tabela 'usuarios' no banco de dados PostgreSQL.
Campos baseados no schema Pydantic UsuarioCompleto (app/schemas.py).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

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
    senha_atualizada_em = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    # UUIDs referenciais
    curso_id = Column(UUID(as_uuid=True), ForeignKey(
        "cursos.id"), nullable=False)
    status_id = Column(UUID(as_uuid=True), ForeignKey(
        "status_usuarios.id"), nullable=False)
    global_role = Column(UUID(as_uuid=True), ForeignKey(
        "cargos.id"), nullable=False)

    # relacao N para 1
    curso = relationship("Course", back_populates="usuarios")
    status = relationship("Status")
    role = relationship("Role")

    def __repr__(self) -> str:
        return f"<User {self.nome_completo} ({self.email})>"
