
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.course import Course
from app.schemas import CursoResumo, ErroPadrao

router = APIRouter(
    prefix="/domain",
    tags=["Dados Gerais do Sistema"],
)


@router.get(
    "/cursos",
    response_model=list[CursoResumo],
    status_code=200,
    summary="Listar cursos",
    description="Retorna a lista de cursos disponíveis com id, nome e status ativo.",
    responses={
        200: {
            "description": "Lista de cursos retornada com sucesso.",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "69224513-2b4e-44f6-847d-236a8a3d5cae",
                            "nome": "ciência da computação",
                            "ativo": True,
                        },
                        {
                            "id": "4dfa2b3d-d496-4d3e-83f7-2bcb06b6a815",
                            "nome": "engenharia civil",
                            "ativo": False,
                        },
                        {
                            "id": "f6a241fa-51f6-43ca-8849-18aff71be14d",
                            "nome": "engenharia de produção",
                            "ativo": True,
                        },
                        {
                            "id": "3a9b258f-4bd4-4699-84b4-97308f32cecf",
                            "nome": "engenharia de software",
                            "ativo": True,
                        },
                        {
                            "id": "f42113c4-dcac-4f1d-8396-5e8d65f46a9b",
                            "nome": "engenharia mecânica",
                            "ativo": False,
                        },
                    ]
                }
            },
        },
        500: {
            "description": "Erro interno do servidor ao consultar os cursos.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "mensagem": "Erro interno ao consultar os cursos."
                    },
                }
            },
        },
    },
)
async def listar_cursos(db: Session = Depends(get_db)) -> list[CursoResumo]:
    cursos = db.query(Course).order_by(Course.nome.asc()).all()

    return [
        CursoResumo(
            id=curso.id,
            nome=curso.nome,
            ativo=curso.ativo,
        )
        for curso in cursos
    ]
