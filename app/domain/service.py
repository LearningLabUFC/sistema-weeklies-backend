from sqlalchemy.orm import Session

from app.domain.schemas import CursoResumo
from app.models.course import Course


def svc_listar_cursos(db: Session) -> list[CursoResumo]:
    cursos = db.query(Course).order_by(Course.nome.asc()).all()

    return [
        CursoResumo(
            id=curso.id,
            nome=curso.nome,
            ativo=curso.ativo,
        )
        for curso in cursos
    ]
