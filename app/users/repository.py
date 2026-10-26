"""Repository — Acesso a dados de Perfil do Usuário."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User


def find_user_by_email_excluding(
    db: Session, email: str, exclude_user_id: UUID
) -> User | None:
    """Busca um usuário por e-mail, excluindo o próprio usuário."""
    return (
        db.query(User)
        .filter(
            User.email == email,
            User.id != exclude_user_id,
        )
        .first()
    )


def update_user(db: Session, user: User) -> User:
    """Persiste as alterações e retorna o usuário atualizado."""
    db.commit()
    db.refresh(user)
    return user
