from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.schemas import ErroPadrao
from app.database import get_db
from app.domain.schemas import CursoResumo
from app.domain.service import svc_listar_cursos

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
                    ]
                }
            },
        },
        500: {
            "description": "Erro interno do servidor ao consultar os cursos.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {"mensagem": "Erro interno ao consultar os cursos."},
                }
            },
        },
    },
)
async def listar_cursos(db: Session = Depends(get_db)) -> list[CursoResumo]:
    return svc_listar_cursos(db)
