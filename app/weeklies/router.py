"""Router — Rotas de Tasks e Weeklies (Fases 2 e 3 do módulo de Weeklies)."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.core.schemas import MensagemResponse
from app.database import get_db
from app.deps import require_role
from app.models.user import User
from app.weeklies.schemas import (
    AddWeeklyTaskRequest,
    ColaboradoresElegiveisResponse,
    CreateTaskAssignmentRequest,
    CreateTaskRequest,
    CreateWeeklyRequest,
    EvaluateWeeklyRequest,
    GlobalDashboardResponse,
    SectorDashboardResponse,
    TaskAssignmentListResponse,
    TaskAssignmentResponse,
    TaskListResponse,
    TaskResponse,
    UpdateTaskPrazoRequest,
    UpdateTaskRequest,
    UpdateWeeklyTaskRequest,
    WeeklyListResponse,
    WeeklyResponse,
    WeeklyTaskItemResponse,
    WeeklyWarningListResponse,
)
from app.weeklies.service import (
    svc_add_task_to_weekly,
    svc_concluir_task_auditoria,
    svc_create_task,
    svc_create_task_assignment,
    svc_create_weekly,
    svc_delete_task,
    svc_evaluate_weekly,
    svc_get_global_dashboard,
    svc_get_sector_dashboard,
    svc_get_weekly_detail,
    svc_list_eligible_collaborators,
    svc_list_my_assignments,
    svc_list_my_tasks,
    svc_list_my_warnings,
    svc_list_my_weeklies,
    svc_list_sector_tasks_in_audit,
    svc_list_sector_warnings,
    svc_list_sector_weeklies,
    svc_obter_ou_criar_weekly_atual,
    svc_reabrir_weekly,
    svc_remove_task_from_weekly,
    svc_respond_task_assignment,
    svc_send_weekly,
    svc_update_task,
    svc_update_task_prazo,
    svc_update_weekly_task,
)

tasks_router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)

weeklies_router = APIRouter(
    prefix="/weeklies",
    tags=["Weeklies"],
)


# ── Rotas de Tasks (Fase 2) ──────────────────────────────────


@tasks_router.post(
    "",
    response_model=TaskResponse,
    status_code=201,
    summary="Criar uma nova task",
    description=(
        "Cria uma nova task para o usuário autenticado dentro de um setor. "
        "Exige vínculo com o setor e janela de submissão aberta."
    ),
)
async def create_task(
    body: CreateTaskRequest,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_create_task(body, current_user, db)


@tasks_router.get(
    "/me",
    response_model=TaskListResponse,
    status_code=200,
    summary="Listar minhas tasks",
    description=(
        "Retorna as tasks do usuário autenticado com paginação. "
        "Pode filtrar por setor e/ou status."
    ),
)
async def list_my_tasks(
    setor_id: UUID | None = Query(
        None, description="Filtrar por setor específico."
    ),
    status: str | None = Query(
        None,
        description="Filtrar por status: PENDENTE, CONCLUIDA, EM_AUDITORIA, REMOVIDA_PELO_LIDER.",
    ),
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(
        20, ge=1, le=100, description="Itens por página (máx. 100)."
    ),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_my_tasks(current_user, db, setor_id, status, pagina, limite)


@tasks_router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=200,
    summary="Editar uma task",
    description=(
        "Atualiza título e/ou descrição de uma task. "
        "Exige proprietário vinculado ao setor, task PENDENTE e janela aberta. "
        "Tasks presentes em relatórios aprovados ou de janelas encerradas "
        "não podem ter seu texto alterado."
    ),
)
async def update_task(
    task_id: UUID,
    body: UpdateTaskRequest,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_update_task(task_id, body, current_user, db)


@tasks_router.patch(
    "/{task_id}/prazo",
    response_model=TaskResponse,
    status_code=200,
    summary="Alterar prazo de conclusão de uma task",
    description="Apenas líder do setor ou admin/super_admin pode alterar o prazo.",
)
async def update_task_prazo(
    task_id: UUID,
    body: UpdateTaskPrazoRequest,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_update_task_prazo(task_id, body, current_user, db)


@tasks_router.delete(
    "/{task_id}",
    response_model=MensagemResponse,
    status_code=200,
    summary="Remover task (soft delete)",
    description=(
        "Marca a task como REMOVIDA_PELO_LIDER. "
        "Apenas líder do setor ou admin/super_admin pode remover."
    ),
)
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_delete_task(task_id, current_user, db)


@tasks_router.get(
    "/setor/{setor_id}/auditoria",
    response_model=TaskListResponse,
    status_code=200,
    summary="Listar tarefas em auditoria do setor",
    description=(
        "Retorna tarefas com status EM_AUDITORIA para líderes do setor ou admins. "
        "Permite monitorar itens vencidos sem ação de líderes há dias."
    ),
)
async def list_sector_tasks_in_audit(
    setor_id: UUID,
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(
        20, ge=1, le=100, description="Itens por página (máx. 100)."
    ),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_sector_tasks_in_audit(
        setor_id, current_user, db, pagina, limite
    )


@tasks_router.patch(
    "/{task_id}/concluir",
    response_model=TaskResponse,
    status_code=200,
    summary="Concluir tarefa sob auditoria ou pendente",
    description=(
        "Permite a líderes do setor ou admins concluir diretamente uma tarefa "
        "em auditoria ou pendente, definindo status como CONCLUIDA."
    ),
)
async def concluir_task_auditoria(
    task_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_concluir_task_auditoria(task_id, current_user, db)


@tasks_router.get(
    "/colaboradores-elegiveis",
    response_model=ColaboradoresElegiveisResponse,
    status_code=200,
    summary="Listar colaboradores elegíveis para tarefas",
    description=(
        "Retorna membros ativos disponíveis para atribuição e colaboração em tarefas. "
        "Permite busca por nome/email e exclusão de conflitos para uma task específica."
    ),
)
async def listar_colaboradores_elegiveis(
    busca: str | None = Query(
        None, description="Busca por nome, e-mail ou matrícula (case-insensitive)."
    ),
    task_id: UUID | None = Query(
        None, description="UUID da tarefa para filtrar conflitos prévios."
    ),
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página (máx. 100)."),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_eligible_collaborators(
        solicitante_id=current_user.id,
        task_id=task_id,
        busca=busca,
        pagina=pagina,
        limite=limite,
        db=db,
    )


@tasks_router.post(
    "/{task_id}/atribuir",
    response_model=TaskAssignmentResponse,
    status_code=201,
    summary="Convidar membro para colaborar na task",
    description=(
        "Envia um convite de atribuição de uma task para outro membro ativo do mesmo setor. "
        "Apenas o proprietário da tarefa ou líder/admin do setor pode convidar."
    ),
)
async def atribuir_task(
    task_id: UUID,
    body: CreateTaskAssignmentRequest,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_create_task_assignment(task_id, body, current_user, db)


@tasks_router.patch(
    "/atribuicoes/{assignment_id}/aceitar",
    response_model=TaskAssignmentResponse,
    status_code=200,
    include_in_schema=False,
)
async def aceitar_atribuicao_tasks_alias(
    assignment_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_respond_task_assignment(
        assignment_id, aceitar=True, current_user=current_user, db=db
    )


@tasks_router.patch(
    "/atribuicoes/{assignment_id}/recusar",
    response_model=TaskAssignmentResponse,
    status_code=200,
    include_in_schema=False,
)
async def recusar_atribuicao_tasks_alias(
    assignment_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_respond_task_assignment(
        assignment_id, aceitar=False, current_user=current_user, db=db
    )


@tasks_router.get(
    "/atribuicoes/me",
    response_model=TaskAssignmentListResponse,
    status_code=200,
    include_in_schema=False,
)
async def list_my_assignments_tasks_alias(
    tipo: str = Query("recebidas", description="Tipo de convite: 'recebidas' ou 'enviadas'."),
    status: str | None = Query(None, description="Filtrar por status: PENDENTE, ACEITA, RECUSADA."),
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página (máx. 100)."),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_my_assignments(
        tipo=tipo, status=status, pagina=pagina, limite=limite, current_user=current_user, db=db
    )



# ── Rotas de Weeklies (Fase 3) ────────────────────────────────


@weeklies_router.get(
    "/me",
    response_model=WeeklyListResponse,
    status_code=200,
    summary="Listar minhas weeklies",
    description=(
        "Lista os relatórios semanais do usuário autenticado com paginação. "
        "Permite filtrar por setor e por status."
    ),
)
async def list_my_weeklies(
    setor_id: UUID | None = Query(
        None, description="Filtrar por setor específico."
    ),
    status: str | None = Query(
        None,
        description="Filtrar por status: RASCUNHO, ENVIADA, APROVADA, REJEITADA.",
    ),
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(
        20, ge=1, le=100, description="Itens por página (máx. 100)."
    ),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_my_weeklies(
        current_user, db, setor_id, status, pagina, limite
    )


@weeklies_router.get(
    "/setor/{setor_id}",
    response_model=WeeklyListResponse,
    status_code=200,
    summary="Listar weeklies de um setor",
    description=(
        "Lista os relatórios semanais do setor especificado. "
        "Apenas líderes do setor ou administradores podem acessar."
    ),
)
async def list_sector_weeklies(
    setor_id: UUID,
    status: str | None = Query(
        None,
        description="Filtrar por status: RASCUNHO, ENVIADA, APROVADA, REJEITADA.",
    ),
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(
        20, ge=1, le=100, description="Itens por página (máx. 100)."
    ),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_sector_weeklies(
        setor_id, status, pagina, limite, current_user, db
    )


@weeklies_router.get(
    "/me/atual",
    response_model=WeeklyResponse,
    status_code=200,
    summary="Obter ou criar weekly da semana atual",
    description=(
        "Retorna a weekly da semana de referência atual para o setor informado. "
        "Se ainda não existir e estiver dentro da janela de submissão (Sex-Seg), "
        "cria automaticamente em RASCUNHO."
    ),
)
async def get_my_current_weekly(
    setor_id: UUID = Query(
        ..., description="UUID do setor para o qual buscar/abrir a weekly."
    ),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_obter_ou_criar_weekly_atual(setor_id, current_user, db)


@weeklies_router.post(
    "",
    response_model=WeeklyResponse,
    status_code=201,
    summary="Criar weekly explicitamente",
    description=(
        "Cria uma weekly em status RASCUNHO para o setor e semana de referência informados. "
        "Exige que o momento esteja dentro da janela de submissão."
    ),
)
async def create_weekly(
    body: CreateWeeklyRequest,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_create_weekly(body, current_user, db)


@weeklies_router.get(
    "/{weekly_id}",
    response_model=WeeklyResponse,
    status_code=200,
    summary="Detalhes de uma weekly",
    description=(
        "Retorna os dados completos da weekly com suas tarefas. "
        "Permitido para o próprio autor, líder do setor da weekly ou administradores."
    ),
)
async def get_weekly_detail(
    weekly_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_weekly_detail(weekly_id, current_user, db)


@weeklies_router.patch(
    "/{weekly_id}/enviar",
    response_model=WeeklyResponse,
    status_code=200,
    summary="Enviar weekly (RASCUNHO → ENVIADA)",
    description=(
        "Transita o relatório semanal de RASCUNHO para ENVIADA. "
        "Só pode ser realizado pelo autor dentro da janela de submissão "
        "e requer pelo menos uma tarefa associada."
    ),
)
async def send_weekly(
    weekly_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_send_weekly(weekly_id, current_user, db)


@weeklies_router.patch(
    "/{weekly_id}/reabrir",
    response_model=WeeklyResponse,
    status_code=200,
    summary="Reabrir weekly (ENVIADA → RASCUNHO)",
    description=(
        "Transita o relatório semanal de ENVIADA de volta para RASCUNHO para permitir ajustes "
        "pelo autor, desde que a janela de submissão ainda esteja aberta e a weekly não tenha sido aprovada."
    ),
)
async def reopen_weekly(
    weekly_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_reabrir_weekly(weekly_id, current_user, db)


@weeklies_router.patch(
    "/{weekly_id}/avaliar",
    response_model=WeeklyResponse,
    status_code=200,
    summary="Avaliar weekly (Aprovar ou Rejeitar)",
    description=(
        "Avalia a weekly (APROVADA ou REJEITADA). "
        "Apenas líderes do setor ou administradores podem executar esta ação."
    ),
)
async def evaluate_weekly(
    weekly_id: UUID,
    body: EvaluateWeeklyRequest,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_evaluate_weekly(weekly_id, body, current_user, db)


@weeklies_router.post(
    "/{weekly_id}/tasks",
    response_model=WeeklyTaskItemResponse,
    status_code=201,
    summary="Adicionar tarefa à weekly",
    description=(
        "Associa uma tarefa à weekly. Pode ser uma tarefa existente "
        "(passando task_id) ou uma nova tarefa criada inline (passando titulo)."
    ),
)
async def add_task_to_weekly(
    weekly_id: UUID,
    body: AddWeeklyTaskRequest,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_add_task_to_weekly(weekly_id, body, current_user, db)


@weeklies_router.patch(
    "/{weekly_id}/tasks/{weekly_task_id}",
    response_model=WeeklyTaskItemResponse,
    status_code=200,
    summary="Atualizar tarefa na weekly",
    description=(
        "Marca a tarefa como concluída e/ou registra um impedimento "
        "no contexto desta weekly."
    ),
)
async def update_weekly_task(
    weekly_id: UUID,
    weekly_task_id: UUID,
    body: UpdateWeeklyTaskRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_update_weekly_task(
        weekly_id,
        weekly_task_id,
        body,
        current_user,
        db,
        background_tasks=background_tasks,
    )



@weeklies_router.delete(
    "/{weekly_id}/tasks/{weekly_task_id}",
    response_model=MensagemResponse,
    status_code=200,
    summary="Remover tarefa da weekly",
    description=(
        "Remove a associação da tarefa com esta weekly. "
        "A tarefa original permanece cadastrada no banco de dados."
    ),
)
async def remove_task_from_weekly(
    weekly_id: UUID,
    weekly_task_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_remove_task_from_weekly(
        weekly_id, weekly_task_id, current_user, db
    )


# ── Rotas de Advertências (Fase 7) ───────────────────────────

advertencias_router = APIRouter(
    prefix="/advertencias",
    tags=["Advertências"],
)


@advertencias_router.get(
    "/setor/{setor_id}",
    response_model=WeeklyWarningListResponse,
    status_code=200,
    summary="Listar advertências de um setor",
    description=(
        "Retorna a lista paginada de advertências emitidas para membros de um setor. "
        "Apenas líderes do setor ou admin/super_admin."
    ),
)
async def list_sector_warnings(
    setor_id: UUID,
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página."),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_sector_warnings(
        setor_id, current_user, db, pagina=pagina, limite=limite
    )


@advertencias_router.get(
    "/me",
    response_model=WeeklyWarningListResponse,
    status_code=200,
    summary="Listar minhas advertências",
    description="Retorna a lista paginada de advertências recebidas pelo usuário autenticado.",
)
async def list_my_warnings(
    setor_id: UUID | None = Query(
        None, description="Filtrar por setor específico."
    ),
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página."),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_my_warnings(
        current_user, db, setor_id=setor_id, pagina=pagina, limite=limite
    )


# ── Rotas de Atribuições de Tasks (Fase 9) ───────────────────

atribuicoes_router = APIRouter(
    prefix="/atribuicoes",
    tags=["Atribuições de Tasks"],
)


@atribuicoes_router.patch(
    "/{assignment_id}/aceitar",
    response_model=TaskAssignmentResponse,
    status_code=200,
    summary="Aceitar convite de colaboração na task",
    description=(
        "Aceita o convite e clona de forma independente a task para o membro convidado, "
        "vinculando-a à sua weekly atual (se estiver em RASCUNHO)."
    ),
)
async def aceitar_atribuicao(
    assignment_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_respond_task_assignment(
        assignment_id, aceitar=True, current_user=current_user, db=db
    )


@atribuicoes_router.patch(
    "/{assignment_id}/recusar",
    response_model=TaskAssignmentResponse,
    status_code=200,
    summary="Recusar convite de colaboração na task",
    description="Recusa o convite de colaboração na task e notifica o solicitante.",
)
async def recusar_atribuicao(
    assignment_id: UUID,
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_respond_task_assignment(
        assignment_id, aceitar=False, current_user=current_user, db=db
    )


@atribuicoes_router.get(
    "/me",
    response_model=TaskAssignmentListResponse,
    status_code=200,
    summary="Listar meus convites de tarefas",
    description=(
        "Retorna a lista paginada de convites de colaboração enviados ou recebidos pelo usuário autenticado."
    ),
)
async def list_my_assignments(
    tipo: str = Query("recebidas", description="Tipo de convite: 'recebidas' ou 'enviadas'."),
    status: str | None = Query(None, description="Filtrar por status: PENDENTE, ACEITA, RECUSADA."),
    pagina: int = Query(1, ge=1, description="Número da página (1-indexed)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página (máx. 100)."),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_list_my_assignments(
        tipo=tipo, status=status, pagina=pagina, limite=limite, current_user=current_user, db=db
    )


# ── Rotas de Dashboard (Fase 11) ─────────────────────────────

dashboard_router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


@dashboard_router.get(
    "/setor/{setor_id}",
    response_model=SectorDashboardResponse,
    status_code=200,
    summary="Dashboard analítico do setor",
    description=(
        "Retorna métricas analíticas e consolidadas de submissão, tarefas e impedimentos "
        "para uma semana de referência. Acesso permitido para líderes do setor e administradores."
    ),
)
async def get_sector_dashboard(
    setor_id: UUID,
    semana_referencia: date | None = Query(
        None, description="Segunda-feira de referência (padrão: semana atual)."
    ),
    current_user: User = Depends(
        require_role(["super_admin", "admin", "usuario"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_sector_dashboard(
        setor_id=setor_id,
        semana_referencia=semana_referencia,
        current_user=current_user,
        db=db,
    )


@dashboard_router.get(
    "/geral",
    response_model=GlobalDashboardResponse,
    status_code=200,
    summary="Dashboard analítico geral (Admin)",
    description=(
        "Retorna métricas consolidadas de todos os setores ativos para a semana indicada. "
        "Acesso restrito a administradores e super administradores."
    ),
)
async def get_global_dashboard(
    semana_referencia: date | None = Query(
        None, description="Segunda-feira de referência (padrão: semana atual)."
    ),
    current_user: User = Depends(
        require_role(["super_admin", "admin"])
    ),
    db: Session = Depends(get_db),
) -> Any:
    return svc_get_global_dashboard(
        semana_referencia=semana_referencia,
        current_user=current_user,
        db=db,
    )


# ── Router Unificado ─────────────────────────────────────────

router = APIRouter()
router.include_router(tasks_router)
router.include_router(weeklies_router)
router.include_router(advertencias_router)
router.include_router(atribuicoes_router)
router.include_router(dashboard_router)


