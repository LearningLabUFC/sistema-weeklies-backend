"""
Modelo ORM — Associação Setor-Usuário.

Tabela associativa 'setor_usuarios' que implementa a relação N:N
entre setores e usuários, com o campo 'papel' para diferenciar
líderes de membros dentro de cada setor.
"""

import uuid

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SectorUser(Base):
    """Modelo ORM para a tabela associativa setor ↔ usuário."""

    __tablename__ = "setor_usuarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    setor_id = Column(
        UUID(as_uuid=True), ForeignKey("setores.id"), nullable=False
    )
    usuario_id = Column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False
    )
    papel = Column(
        String(20), nullable=False, default="membro"
    )  # "lider" ou "membro"

    # Relationships
    setor = relationship("Sector", back_populates="usuarios")
    usuario = relationship("User", back_populates="setores")

    __table_args__ = (
        UniqueConstraint("setor_id", "usuario_id", name="uq_setor_usuario"),
    )

    def __repr__(self) -> str:
        return f"<SectorUser setor={self.setor_id} user={self.usuario_id} papel={self.papel}>"
