from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.schemas import ErroPadrao
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.work_session import WorkSessionStatus
from app.work_sessions.schemas import (
    CurrentWorkSessionResponse,
    MetricsSectorsResponse,
    MetricsSummaryResponse,
    MetricsTimelineResponse,
    MetricsUsersResponse,
    PauseItem,
    StartWorkSessionRequest,
    WorkSessionDetail,
    WorkSessionItem,
    WorkSessionListResponse,
    WorkSessionSummaryResponse,
)
from app.work_sessions.service import (
    svc_continue_work_session,
    svc_end_pause,
    svc_end_work_session,
    svc_get_current_work_session,
    svc_get_metrics_sectors,
    svc_get_metrics_summary,
    svc_get_metrics_timeline,
    svc_get_metrics_users,
    svc_get_work_session,
    svc_get_work_session_summary,
    svc_get_work_sessions,
    svc_start_pause,
    svc_start_work_session,
)

router = APIRouter(
    prefix="/work-sessions",
    tags=["Controle de Horas"]
)

@router.post(
    "",
    status_code=201,
    response_model=WorkSessionItem,
    summary="Iniciar registro de hora",
    description=(
        "Inicia um registro de hora para o usuário autenticado.\n"
        "Se o usuário já tiver uma sessão ativa, lança um erro.\n"
        "Se o setor informado não for válido, lança um erro.\n"
        "Se o setor não pertencer ao perfil do usuário, lança um erro.\n"
        "Retorna a sessão de trabalho criada."
    ),
    responses={
        401: {
            "description": "Usuário não autenticado.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "usuarioNaoAutenticado": {
                            "summary": "Usuário não autenticado",
                            "value": {
                                "mensagem": "Usuário não autenticado."
                            },
                        },
                    },
                },
            },
        },
        403: {
            "description": "Setor invalido ou não pertence ao perfil do usuário",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "setorInvalido": {
                            "summary": "Setor inválido",
                            "value": {
                                "mensagem": "Setor inválido."
                            },
                        },
                        "setorNaoPertenceAoPerfil": {
                            "summary": "Setor não pertence ao perfil do usuário",
                            "value": {
                                "mensagem": "Setor não pertence ao perfil do usuário."
                            },
                        },
                    },
                },
            },
        },
        404: {
            "description": "Setor não encontrado",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "setorNaoEncontrado": {
                            "summary": "Setor não encontrado",
                            "value": {
                                "mensagem": "Setor não encontrado."
                            },
                        },
                    },
                },
            },
        },
        409: {
            "description": "Usuário já possui uma sessão ativa.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "sessaoAtiva": {
                            "summary": "Usuário já possui uma sessão ativa",
                            "value": {
                                "mensagem": "Usuário já possui uma sessão ativa."
                            },
                        },
                    },
                },
            },
        },
    },
)
def start_work_session(
    body: StartWorkSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    return svc_start_work_session(body, current_user, db)

@router.post(
    "/{session_id}/pauses",
    status_code=201,
    response_model=PauseItem,
    summary="Iniciar pausa na sessão de trabalho",
    description=(
        "Inicia uma pausa na sessão de trabalho do usuário autenticado."
    ),
    responses={
        403: {
            "description": "Sessão não pertence ao usuário autenticado.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "mensagem": "Sessão não pertence ao perfil do usuário."
                    },
                },
            },
        },
        404: {
            "description": "Sessão de trabalho não encontrada.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "mensagem": "Sessão de trabalho não encontrada."
                    },
                },
            },
        },
        409: {
            "description": "Não é possível iniciar uma nova pausa.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "sessaoNaoAtiva": {
                            "summary": "Sessão não está ativa",
                            "value": {
                                "mensagem": "A sessão de trabalho não está ativa."
                            },
                        },
                        "pausaJaAtiva": {
                            "summary": "Pausa já ativa",
                            "value": {
                                "mensagem": "A sessão já possui uma pausa ativa."
                            },
                        },
                    },
                },
            },
        },
    },
)
def start_pause(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PauseItem:
    return svc_start_pause(session_id, current_user, db)

@router.patch(
    "/{session_id}/pauses/{pause_id}/end",
    status_code=200,
    response_model=PauseItem,
    summary="Encerrar pausa na sessão de trabalho",
    description=(
        "Encerra uma pausa na sessão de trabalho do usuário autenticado."
    ),
    responses={
        403: {
            "description": "Pausa não pertence ao usuário autenticado.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "mensagem": "Pausa não pertence ao perfil do usuário."
                    },
                },
            },
        },
        404: {
            "description": "Pausa não encontrada.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "mensagem": "Pausa não encontrada."
                    },
                },
            },
        },
        409: {
            "description": "A pausa já foi encerrada.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "examples": {
                        "pausaJaEncerrada": {
                            "summary": "Pausa já foi encerrada",
                            "value": {
                                "mensagem": "A pausa já foi encerrada."
                            },
                        },
                    },
                },
            },
        },
    },
)
def end_pause(
    session_id: UUID,
    pause_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PauseItem:
    return svc_end_pause(session_id, pause_id, current_user, db)

@router.patch(
    "/{session_id}/end",
    status_code=200,
    response_model=WorkSessionItem,
    summary="Encerrar sessão de trabalho",
    description=(
        "Encerra a sessão de trabalho do usuário autenticado. "
        "Caso exista uma pausa aberta, ela também será encerrada."
    ),
    responses={
        403: {
            "description": "Sessão não pertence ao usuário autenticado.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "mensagem": "Sessão não pertence ao perfil do usuário."
                    },
                },
            },
        },
        404: {
            "description": "Sessão de trabalho não encontrada.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "mensagem": "Sessão de trabalho não encontrada."
                    },
                },
            },
        },
        409: {
            "description": "A sessão já foi encerrada.",
            "content": {
                "application/json": {
                    "schema": ErroPadrao.model_json_schema(),
                    "example": {
                        "sessaoJaEncerrada": {
                            "summary": "Sessão já foi encerrada",
                            "value": {
                                "mensagem": "A sessão já foi encerrada."
                            },
                        },
                    },
                },
            },
        },
    },
)
def end_work_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_end_work_session(session_id, current_user, db)

@router.patch(
    "/{session_id}/continue",
    status_code=200,
    response_model=WorkSessionItem,
    summary="Prorrogar sessão de trabalho",
    description=(
        "Prorroga o horário de expiração da sessão ativa do usuário autenticado."
    ),
    responses={
        403: {
            "description": "Sessão não pertence ao usuário autenticado.",
            "model": ErroPadrao,
        },
        404: {
            "description": "Sessão de trabalho não encontrada.",
            "model": ErroPadrao,
        },
        409: {
            "description": (
                "Sessão já encerrada, expirada ou impossibilitada de ser prorrogada."
            ),
            "model": ErroPadrao,
        },
    },
)
def continue_work_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_continue_work_session(
        session_id,
        current_user,
        db,
    )

@router.get("/current",
            response_model=CurrentWorkSessionResponse, 
            status_code=200,
            summary="Obter sessão de trabalho atual",
            description=(
                "Obtém a sessão de trabalho atual do usuário autenticado."
            ),
)
def get_current_work_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_current_work_session(current_user, db)

@router.get(
    "/summary",
    response_model=WorkSessionSummaryResponse,
    status_code=200,
    summary="Obter tempo trabalhado em um período",
    description=(
        "Obtém o tempo trabalhado em um período. "
        "Pode filtrar por usuário e setor."
    ),
)
def get_work_session_summary(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = Query(
        None,
        description=(
            "Filtrar por usuário. Para usuários comuns, se omitido, "
            "utiliza o usuário autenticado. Admin e super_admin, "
            "se omitirem, consultam todos os usuários."
        ),
    ),
    setor_id: UUID | None = Query(
        None,
        description=(
            "Filtrar por setor. Se omitido, não filtra por setor."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_work_session_summary(
        inicio,
        fim,
        usuario_id,
        setor_id,
        current_user,
        db,
    )

@router.get(
    "",
    response_model=WorkSessionListResponse,
    status_code=200,
    summary="Listar sessões de trabalho",
    description=(
        "Lista o histórico de sessões de trabalho com paginação "
        "e filtros opcionais por usuário, setor, status e período."
    ),
)
def get_work_sessions(
    usuario_id: UUID | None = Query(
        None,
        description="Filtrar por usuário. Se omitido, utiliza o usuário autenticado.",
    ),
    setor_id: UUID | None = Query(
        None,
        description="Filtrar por setor.",
    ),
    status: WorkSessionStatus | None = Query(
        None,
        description="Filtrar por status da sessão.",
    ),
    inicio: datetime | None = Query(
        None,
        description="Data e hora inicial do período.",
    ),
    fim: datetime | None = Query(
        None,
        description="Data e hora final do período.",
    ),
    pagina: int = Query(
        1,
        ge=1,
        description="Número da página.",
    ),
    limite: int = Query(
        20,
        ge=1,
        le=100,
        description="Quantidade de itens por página.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_work_sessions(
        usuario_id=usuario_id,
        setor_id=setor_id,
        status=status,
        inicio=inicio,
        fim=fim,
        pagina=pagina,
        limite=limite,
        current_user=current_user,
        db=db,
    )

@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryResponse,
    status_code=200,
    summary="Obter resumo das métricas administrativas",
)
def get_metrics_summary(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = Query(None),
    setor_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_metrics_summary(
        inicio,
        fim,
        usuario_id,
        setor_id,
        current_user,
        db,
    )

@router.get(
    "/metrics/users",
    response_model=MetricsUsersResponse,
    status_code=200,
    summary="Obter métricas agrupadas por usuário",
)
def get_metrics_users(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = Query(None),
    setor_id: UUID | None = Query(None),
    pagina: int = Query(1, ge=1),
    limite: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_metrics_users(
        inicio,
        fim,
        usuario_id,
        setor_id,
        pagina,
        limite,
        current_user,
        db,
    )

@router.get(
    "/metrics/sectors",
    response_model=MetricsSectorsResponse,
    status_code=200,
    summary="Obter métricas agrupadas por setor",
)
def get_metrics_sectors(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = Query(None),
    setor_id: UUID | None = Query(None),
    pagina: int = Query(1, ge=1),
    limite: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_metrics_sectors(
        inicio,
        fim,
        usuario_id,
        setor_id,
        pagina,
        limite,
        current_user,
        db,
    )

@router.get(
    "/metrics/timeline",
    response_model=MetricsTimelineResponse,
    status_code=200,
    summary="Obter timeline das métricas administrativas",
    description=(
        "Retorna o tempo trabalhado e pausado "
        "agrupado por dia, semana ou mês."
    ),
)
def get_metrics_timeline(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = Query(
        None,
        description="Filtrar por usuário.",
    ),
    setor_id: UUID | None = Query(
        None,
        description="Filtrar por setor.",
    ),
    agrupamento: str = Query(
        "dia",
        description=(
            "Agrupamento da timeline: "
            "dia, semana ou mes."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_metrics_timeline(
        inicio=inicio,
        fim=fim,
        usuario_id=usuario_id,
        setor_id=setor_id,
        agrupamento=agrupamento,
        current_user=current_user,
        db=db,
    )

@router.get("/{session_id}",
            response_model=WorkSessionDetail,
            status_code=200,
            summary="Obter sessão de trabalho detalhada",
            description=(
                "Obtém a sessão de trabalho detalhada."
            ),
            responses={
                403: {
                    "description": "Sessão não pertence ao usuário autenticado.",
                    "content": {
                        "application/json": {
                            "schema": ErroPadrao.model_json_schema(),
                            "example": {
                                "mensagem": "Sessão não pertence ao perfil do usuário."
                            },
                        },
                    },
                },
                404: {
                    "description": "Sessão de trabalho não encontrada.",
                    "content": {
                        "application/json": {
                            "schema": ErroPadrao.model_json_schema(),
                            "example": {
                                "mensagem": "Sessão de trabalho não encontrada."
                            },
                        },
                    },
                },
            },
)
def get_work_session_detail(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_work_session(session_id, current_user, db)

    
