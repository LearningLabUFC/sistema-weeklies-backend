"""Repository — Acesso a dados de Setores."""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.user import User

# ── Setor ────────────────────────────────────────────────────


def create_sector(db: Session, sector: Sector) -> Sector:
    """Persiste um novo setor no banco."""
    db.add(sector)
    db.commit()
    db.refresh(sector)
    return sector


def find_sector_by_id(db: Session, sector_id: UUID) -> Sector | None:
    return db.query(Sector).filter(Sector.id == sector_id).first()


def find_sector_by_name(db: Session, nome: str) -> Sector | None:
    return db.query(Sector).filter(Sector.nome == nome).first()


def list_sectors_paginated(
    db: Session,
    pagina: int,
    limite: int,
) -> tuple[list[Sector], int]:
    """Retorna (lista_de_setores, total) com paginação."""
    query = db.query(Sector)
    total = query.count()
    offset = (pagina - 1) * limite
    setores = query.order_by(Sector.nome.asc()).offset(offset).limit(limite).all()
    return setores, total


def update_sector(db: Session) -> None:
    """Persiste as alterações feitas nos objetos Sector."""
    db.commit()


# ── Contagens ────────────────────────────────────────────────


def count_members_by_sector(db: Session, sector_id: UUID) -> int:
    """Conta membros (papel='membro') em um setor."""
    return (
        db.query(func.count(SectorUser.id))
        .filter(SectorUser.setor_id == sector_id, SectorUser.papel == "membro")
        .scalar()
    )


def count_leaders_by_sector(db: Session, sector_id: UUID) -> int:
    """Conta líderes (papel='lider') em um setor."""
    return (
        db.query(func.count(SectorUser.id))
        .filter(SectorUser.setor_id == sector_id, SectorUser.papel == "lider")
        .scalar()
    )


# ── Membros do Setor ────────────────────────────────────────


def find_sector_user(db: Session, sector_id: UUID, user_id: UUID) -> SectorUser | None:
    """Busca a associação de um usuário em um setor."""
    return (
        db.query(SectorUser)
        .filter(
            SectorUser.setor_id == sector_id,
            SectorUser.usuario_id == user_id,
        )
        .first()
    )


def list_sector_members(db: Session, sector_id: UUID) -> list[SectorUser]:
    """Lista todos os membros/líderes de um setor com dados do usuário."""
    return db.query(SectorUser).filter(SectorUser.setor_id == sector_id).all()


def add_member_to_sector(db: Session, sector_user: SectorUser) -> SectorUser:
    """Adiciona um usuário a um setor."""
    db.add(sector_user)
    db.commit()
    db.refresh(sector_user)
    return sector_user


def remove_member_from_sector(db: Session, sector_user: SectorUser) -> None:
    """Remove um usuário de um setor."""
    db.delete(sector_user)
    db.commit()


def find_user_by_id(db: Session, user_id: UUID) -> User | None:
    """Busca um usuário pelo ID."""
    return db.query(User).filter(User.id == user_id).first()
