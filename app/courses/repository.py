"""Repository — Acesso a dados de Cursos."""

from sqlalchemy.orm import Session

from app.models.course import Course


def list_all_courses_ordered(db: Session) -> list[Course]:
    """Retorna todos os cursos ordenados por nome."""
    return db.query(Course).order_by(Course.nome.asc()).all()
