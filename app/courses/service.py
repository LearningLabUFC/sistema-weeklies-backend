from sqlalchemy.orm import Session

from app.courses.repository import list_all_courses_ordered
from app.courses.schemas import CursoResumo


def svc_listar_cursos(db: Session) -> list[CursoResumo]:
    cursos = list_all_courses_ordered(db)

    return [
        CursoResumo(
            id=curso.id,
            nome=curso.nome,
            ativo=curso.ativo,
        )
        for curso in cursos
    ]
