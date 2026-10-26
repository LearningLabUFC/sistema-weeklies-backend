"""Repository — Acesso a dados de Autenticação."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def find_user_by_matricula(db: Session, matricula: str) -> User | None:
    return db.query(User).filter(User.matricula == matricula).first()


def find_user_by_id(db: Session, user_id: str | UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user: User) -> User:
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User) -> None:
    """Persiste as alterações feitas no objeto User."""
    db.commit()
