"""Repository — Acesso a dados de Administração."""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.status import Status
from app.models.user import User


def find_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def list_users_paginated(
    db: Session,
    pagina: int,
    limite: int,
    status_filtro: str | None,
    role_filtro: str | None,
    busca: str | None,
) -> tuple[list[User], int]:
    """Retorna (lista_de_usuarios, total) com filtros e paginação."""
    query = db.query(User)

    if status_filtro:
        query = query.join(Status, User.status_id == Status.id).filter(
            Status.nome == status_filtro
        )

    if role_filtro:
        query = query.join(Role, User.global_role == Role.id).filter(
            Role.nome == role_filtro
        )

    if busca:
        termo = f"%{busca}%"
        query = query.filter(
            (func.lower(User.nome_completo).like(func.lower(termo)))
            | (func.lower(User.email).like(func.lower(termo)))
        )

    total = query.count()
    offset = (pagina - 1) * limite
    usuarios = (
        query.order_by(User.nome_completo.asc()).offset(offset).limit(limite).all()
    )
    return usuarios, total


def list_pending_users(db: Session) -> list[User]:
    return db.query(User).join(Status).filter(Status.nome == "pendente").all()


def find_status_by_name(db: Session, name: str) -> Status | None:
    return db.query(Status).filter(Status.nome == name).first()


def find_role_by_name(db: Session, name: str) -> Role | None:
    return db.query(Role).filter(Role.nome == name).first()


def count_active_admins(db: Session) -> int:
    """Conta quantos admins/super_admins ativos existem no sistema."""
    roles_admin = db.query(Role.id).filter(Role.nome.in_(["admin", "super_admin"]))
    status_ativo = db.query(Status.id).filter(Status.nome == "ativo").scalar()

    return (
        db.query(func.count(User.id))
        .filter(
            User.global_role.in_(roles_admin.subquery().select()),
            User.status_id == status_ativo,
        )
        .scalar()
    )


def update_user(db: Session) -> None:
    """Persiste as alterações feitas nos objetos User."""
    db.commit()
