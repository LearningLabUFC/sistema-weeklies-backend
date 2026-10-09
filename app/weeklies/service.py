import logging
import smtplib
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger("uvicorn.error")

from app.config import settings
from app.core.constants import RoleID, StatusID
from app.core.email import (
    enviar_email_advertencia,
    enviar_email_convite_task,
    enviar_email_escalonamento_auditoria,
    enviar_email_impedimento,
    enviar_email_resposta_convite_task,
    enviar_email_task_auditoria,
)
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.schemas import MensagemResponse
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.models.weekly_warning import WeeklyWarning
from app.weeklies.repository import (
    add_task_to_weekly,
    commit_changes,
    count_active_members_by_sector,
    count_pending_tasks_by_sector,
    count_tasks_in_audit_by_sector,
    create_task,
    create_task_assignment,
    create_weekly,
    delete_task_soft,
    find_active_sector_members,
    find_admin_users,
    find_all_active_sectors,
    find_assignment_by_id,
    find_eligible_collaborators,
    find_expired_pending_tasks,
    find_pending_assignment_by_task_and_user,
    find_pending_tasks_for_rollover,
    find_sector_by_id,
    find_sector_leaders,
    find_sector_user,
    find_task_by_id,
    find_tasks_in_audit,
    find_warning_by_user_sector_semana,
    find_weeklies_by_sector_and_semana,
    find_weekly_by_id,
    find_weekly_by_user_sector_semana,
    find_weekly_task,
    find_weekly_task_by_id,
    get_next_weekly_task_posicao,
    list_assignments_by_user,
    list_tasks_by_user,
    list_tasks_by_user_sector,
    list_warnings_by_sector,
    list_warnings_by_user,
    list_weeklies_by_sector,
    list_weeklies_by_user,
    remove_task_from_weekly,
    update_task,
)
from app.weeklies.schemas import (
    AddWeeklyTaskRequest,
    ColaboradorElegivelItem,
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
    WeeklySummaryResponse,
    WeeklyTaskItemResponse,
    WeeklyWarningListResponse,
    WeeklyWarningResponse,
)
from app.weeklies.timezone_utils import (
    FUSO_LLAB,
    dentro_da_janela,
    get_now_fortaleza,
    obter_semana_referencia,
    validar_janela_submissao,
)

TASK_STATUS_VALIDOS = {"PENDENTE", "CONCLUIDA", "EM_AUDITORIA", "REMOVIDA_PELO_LIDER"}
WEEKLY_STATUS_VALIDOS = {"RASCUNHO", "ENVIADA", "APROVADA", "REJEITADA", "EXPIRADA"}
DEFAULT_PRAZO_DIAS = settings.WEEKLY_TASK_DEFAULT_DEADLINE_DAYS


# ── Helpers de Autorização e Validação ────────────────────────


def _verificar_vinculo_setor(db: Session, setor_id: UUID, usuario_id: UUID) -> None:
    """Garante que o setor existe e está ativo, e que o usuário está vinculado a ele.
    Levanta NotFoundError se o setor não existir, BadRequestError se estiver inativo,
    ou ForbiddenError caso o usuário não esteja vinculado.
    """
    sector = find_sector_by_id(db, setor_id)
    if not sector:
        raise NotFoundError("Setor não encontrado.")
    if not sector.ativo:
        raise BadRequestError("Este setor está inativo.")

    assoc = find_sector_user(db, setor_id, usuario_id)
    if not assoc:
        raise ForbiddenError("Você não está vinculado a este setor.")


def _verificar_proprietario_task(task: Task, usuario: User) -> None:
    """Garante que o usuário é o dono da task. Levanta ForbiddenError caso contrário."""
    if task.usuario_id != usuario.id:
        raise ForbiddenError("Você não tem permissão para alterar esta task.")


def _verificar_proprietario_weekly(weekly: Weekly, usuario: User) -> None:
    """Garante que o usuário é o dono da weekly. Levanta ForbiddenError caso contrário."""
    if weekly.usuario_id != usuario.id:
        raise ForbiddenError("Você não tem permissão para alterar esta weekly.")


def _validar_escrita_weekly(weekly: Weekly, usuario: User, db: Session) -> None:
    """Validação comum a todas as alterações do autor sobre uma weekly."""
    _verificar_proprietario_weekly(weekly, usuario)
    _verificar_vinculo_setor(db, weekly.setor_id, usuario.id)
    if weekly.status not in ("RASCUNHO", "REJEITADA"):
        raise BadRequestError(
            f"Não é possível alterar uma weekly com status '{weekly.status}'. "
            "Apenas weeklies em 'RASCUNHO' ou 'REJEITADA' podem ser alteradas (reabra para edição se necessário)."
        )
    if weekly.status == "REJEITADA":
        if weekly.avaliada_em:
            agora = get_now_fortaleza()
            avaliada_tz = weekly.avaliada_em if weekly.avaliada_em.tzinfo else weekly.avaliada_em.replace(tzinfo=timezone.utc)
            limite_carencia = avaliada_tz.astimezone(FUSO_LLAB) + timedelta(hours=24)
            if agora > limite_carencia:
                raise BadRequestError(
                    "O prazo de carência de 24h para correção desta weekly rejeitada expirou."
                )
    else:
        validar_janela_submissao(semana_referencia=weekly.semana_referencia)


def _is_admin(usuario: User | None) -> bool:
    """Retorna True se o usuário possui cargo global de admin ou super_admin."""
    if not usuario:
        return False
    return usuario.global_role in (RoleID.ADMIN, RoleID.SUPER_ADMIN) or bool(
        usuario.role and usuario.role.nome in ("admin", "super_admin")
    )


def _is_lider_do_setor(db: Session, setor_id: UUID, usuario: User | None) -> bool:
    """Retorna True se o usuário possui papel de líder no setor informado."""
    if not usuario:
        return False
    assoc = find_sector_user(db, setor_id, usuario.id)
    return assoc is not None and assoc.papel == "lider"


def _format_weekly_task_item(weekly_task: WeeklyTask) -> WeeklyTaskItemResponse:
    """Monta a resposta de um item WeeklyTask projetando dados da Task associada,
    priorizando o snapshot histórico se o relatório já foi enviado ou aprovado.
    """
    titulo = (
        weekly_task.snapshot_titulo
        if weekly_task.snapshot_titulo is not None
        else (weekly_task.task.titulo if weekly_task.task else "")
    )
    descricao = (
        weekly_task.snapshot_descricao
        if weekly_task.snapshot_descricao is not None
        else (weekly_task.task.descricao if weekly_task.task else None)
    )
    prazo = (
        weekly_task.snapshot_prazo_conclusao
        if weekly_task.snapshot_prazo_conclusao is not None
        else (weekly_task.task.prazo_conclusao if weekly_task.task else None)
    )
    return WeeklyTaskItemResponse(
        id=weekly_task.id,
        task_id=weekly_task.task_id,
        titulo=titulo,
        descricao=descricao,
        status_task=weekly_task.task.status if weekly_task.task else "PENDENTE",
        prazo_conclusao=prazo,
        concluida=weekly_task.concluida,
        impedimento=weekly_task.impedimento,
        posicao=weekly_task.posicao,
        origem=weekly_task.origem,
    )


def _format_weekly_response(weekly: Weekly) -> WeeklyResponse:
    """Monta a representação completa de uma Weekly com suas tarefas ordenadas."""
    tarefas_ordenadas = sorted(weekly.weekly_tasks, key=lambda item: item.posicao)
    return WeeklyResponse(
        id=weekly.id,
        usuario_id=weekly.usuario_id,
        membro_nome=weekly.usuario.nome_completo if weekly.usuario else None,
        setor_id=weekly.setor_id,
        semana_referencia=weekly.semana_referencia,
        status=weekly.status,
        enviada_em=weekly.enviada_em,
        avaliada_em=weekly.avaliada_em,
        avaliada_por=weekly.avaliada_por,
        observacao_lider=weekly.observacao_lider,
        motivo_expiracao=weekly.motivo_expiracao,
        detalhe_expiracao=weekly.detalhe_expiracao,
        criado_em=weekly.criado_em,
        atualizado_em=weekly.atualizado_em,
        tasks=[_format_weekly_task_item(item) for item in tarefas_ordenadas],
    )


# ── CRUD de Tasks (Fase 2) ───────────────────────────────────


def svc_create_task(
    body: CreateTaskRequest, current_user: User, db: Session
) -> TaskResponse:
    """Cria uma nova task para o usuário autenticado no setor informado."""
    _verificar_vinculo_setor(db, body.setor_id, current_user.id)
    validar_janela_submissao()

    if body.prazo_conclusao and body.prazo_conclusao < get_now_fortaleza().date():
        raise BadRequestError("O prazo de conclusão não pode ser uma data no passado.")

    prazo = body.prazo_conclusao or (
        get_now_fortaleza().date() + timedelta(days=settings.WEEKLY_TASK_DEFAULT_DEADLINE_DAYS)
    )

    nova_task = Task(
        usuario_id=current_user.id,
        setor_id=body.setor_id,
        titulo=body.titulo.strip(),
        descricao=body.descricao,
        prazo_conclusao=prazo,
    )

    task_criada = create_task(db, nova_task)
    return TaskResponse.model_validate(task_criada)


def svc_list_my_tasks(
    current_user: User,
    db: Session,
    setor_id: UUID | None = None,
    status_filter: str | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> TaskListResponse:
    """Lista as tasks do usuário autenticado, opcionalmente filtradas por setor e status."""
    if status_filter and status_filter not in TASK_STATUS_VALIDOS:
        raise BadRequestError(
            f"Status '{status_filter}' inválido. Valores aceitos: {', '.join(sorted(TASK_STATUS_VALIDOS))}."
        )

    if setor_id:
        _verificar_vinculo_setor(db, setor_id, current_user.id)
        tasks, total = list_tasks_by_user_sector(
            db, current_user.id, setor_id, status_filter, pagina, limite
        )
    else:
        tasks, total = list_tasks_by_user(
            db, current_user.id, status_filter, pagina, limite
        )

    return TaskListResponse(
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_update_task(
    task_id: UUID, body: UpdateTaskRequest, current_user: User, db: Session
) -> TaskResponse:
    """
    Atualiza título e/ou descrição de uma task.
    Segurança: O setor_id é obtido da task carregada do banco (Garantia 1).
    Exige proprietário vinculado ao setor, janela aberta e ausência de
    relatórios aprovados ou de outras janelas que compartilhem seu texto.
    """
    task = find_task_by_id(db, task_id, for_update=True)
    if not task:
        raise NotFoundError("Task não encontrada.")

    _verificar_proprietario_task(task, current_user)
    _verificar_vinculo_setor(db, task.setor_id, current_user.id)

    if task.status != "PENDENTE":
        raise BadRequestError(
            f"Não é possível editar uma task com status '{task.status}'."
        )

    # A Task compartilha seu texto com todas as weeklies associadas.
    # Lock ordenado de todas as weeklies associadas antes de validar o status de escrita
    # para evitar deadlocks e garantir coerência com avaliações concorrentes.
    weeklies = (
        db.query(Weekly)
        .join(WeeklyTask, WeeklyTask.weekly_id == Weekly.id)
        .filter(WeeklyTask.task_id == task.id)
        .order_by(Weekly.id)
        .with_for_update()
        .all()
    )
    for weekly in weeklies:
        if weekly.status in ("ENVIADA", "APROVADA", "EXPIRADA"):
            raise BadRequestError(
                f"Não é possível editar uma task presente em uma weekly com status '{weekly.status}'."
            )
        if weekly.status == "REJEITADA":
            if weekly.avaliada_em:
                agora = get_now_fortaleza()
                avaliada_tz = weekly.avaliada_em if weekly.avaliada_em.tzinfo else weekly.avaliada_em.replace(tzinfo=timezone.utc)
                limite_carencia = avaliada_tz.astimezone(FUSO_LLAB) + timedelta(hours=24)
                if agora > limite_carencia:
                    raise BadRequestError(
                        "O prazo de carência de 24h para correção da weekly rejeitada associada expirou."
                    )
        else:
            validar_janela_submissao(semana_referencia=weekly.semana_referencia)

    # Se a task estiver vinculada a uma weekly rejeitada, a edição do texto é permitida
    # fora da janela de submissão para possibilitar atender correções solicitadas pela liderança.
    tem_weekly_rejeitada = any(w.status == "REJEITADA" for w in weeklies)
    if not tem_weekly_rejeitada:
        validar_janela_submissao()

    if "titulo" in body.model_fields_set:
        if body.titulo is None or not body.titulo.strip():
            raise BadRequestError(
                "O título da task não pode ser vazio ou conter apenas espaços em branco."
            )
        task.titulo = body.titulo.strip()
    if "descricao" in body.model_fields_set:
        task.descricao = body.descricao.strip() if body.descricao else None

    update_task(db)
    return TaskResponse.model_validate(task)


def svc_update_task_prazo(
    task_id: UUID, body: UpdateTaskPrazoRequest, current_user: User, db: Session
) -> TaskResponse:
    """
    Atualiza o prazo de conclusão de uma task.
    Apenas líder do setor ou admin/super_admin pode alterar.
    """
    task = find_task_by_id(db, task_id)
    if not task:
        raise NotFoundError("Task não encontrada.")

    if not (_is_admin(current_user) or _is_lider_do_setor(db, task.setor_id, current_user)):
        raise ForbiddenError("Apenas o líder do setor ou admin pode alterar o prazo.")

    if task.status == "EM_AUDITORIA" and task.usuario_id == current_user.id:
        raise ForbiddenError(
            "Você não pode alterar o prazo da sua própria tarefa em auditoria."
        )

    if (
        task.status == "EM_AUDITORIA"
        and _is_lider_do_setor(db, task.setor_id, task.usuario)
        and not _is_admin(current_user)
    ):
        raise ForbiddenError(
            "O prazo de tarefas de líderes em auditoria só pode ser alterado por administradores."
        )

    if task.status == "REMOVIDA_PELO_LIDER":
        raise BadRequestError("Não é possível alterar o prazo de uma task removida.")

    if task.status == "CONCLUIDA":
        raise BadRequestError("Não é possível alterar o prazo de uma task já concluída.")

    if body.prazo_conclusao < get_now_fortaleza().date():
        raise BadRequestError("O novo prazo de conclusão não pode ser uma data no passado.")

    task.prazo_conclusao = body.prazo_conclusao
    if task.status == "EM_AUDITORIA":
        task.status = "PENDENTE"
        task.entrada_auditoria_em = None

    update_task(db)
    return TaskResponse.model_validate(task)


def svc_delete_task(
    task_id: UUID, current_user: User, db: Session
) -> MensagemResponse:
    """
    Soft delete: marca task como REMOVIDA_PELO_LIDER.
    Apenas líder do setor ou admin/super_admin pode remover.
    """
    task = find_task_by_id(db, task_id, for_update=True)
    if not task:
        raise NotFoundError("Task não encontrada.")

    if not (_is_admin(current_user) or _is_lider_do_setor(db, task.setor_id, current_user)):
        raise ForbiddenError("Apenas o líder do setor ou admin pode remover tasks.")

    if task.status == "REMOVIDA_PELO_LIDER":
        raise BadRequestError("Esta task já foi removida.")

    if task.status == "CONCLUIDA":
        raise BadRequestError("Não é possível remover uma task já concluída.")

    delete_task_soft(db, task, current_user.id)

    # Invalida convites pendentes associados a esta tarefa removida
    db.query(TaskAssignment).filter(
        TaskAssignment.task_id == task.id,
        TaskAssignment.status == "PENDENTE",
    ).update({TaskAssignment.status: "EXPIRADA"}, synchronize_session=False)
    commit_changes(db)

    return MensagemResponse(mensagem=f"Task '{task.titulo}' removida com sucesso.")


# ── Ciclo de Vida de Weeklies (Fase 3) ────────────────────────


def criar_weekly_com_rollover(
    db: Session, usuario_id: UUID, setor_id: UUID, semana_referencia: date
) -> Weekly:
    """
    Cria uma nova weekly em RASCUNHO e herda tarefas PENDENTES do membro no setor (Fase 4 - Rollover).
    Atribui às tarefas herdadas origem='HERDADA', concluida=False e posições sequenciais.
    Toda a operação é realizada de forma atômica em uma única transação.
    """
    try:
        nova_weekly = Weekly(
            usuario_id=usuario_id,
            setor_id=setor_id,
            semana_referencia=semana_referencia,
            status="RASCUNHO",
        )
        create_weekly(db, nova_weekly, commit=False)

        # Buscar tarefas PENDENTES do membro neste setor
        tasks_pendentes = find_pending_tasks_for_rollover(db, usuario_id, setor_id)
        for idx, task in enumerate(tasks_pendentes, start=1):
            novo_item = WeeklyTask(
                weekly_id=nova_weekly.id,
                task_id=task.id,
                task=task,
                concluida=False,
                impedimento=None,
                posicao=idx,
                origem="HERDADA",
            )
            add_task_to_weekly(db, novo_item, commit=False)

        db.commit()
        weekly_carregada = find_weekly_by_id(db, nova_weekly.id)
        return weekly_carregada or nova_weekly
    except Exception:
        db.rollback()
        raise


def svc_obter_ou_criar_weekly_atual(
    setor_id: UUID, current_user: User, db: Session
) -> WeeklyResponse:
    """
    Obtém a weekly da semana de referência atual para o setor informado.
    Se ainda não existir e estiver dentro da janela de submissão, cria automaticamente em RASCUNHO
    com herança (rollover) de tarefas pendentes (Fase 4).
    """
    _verificar_vinculo_setor(db, setor_id, current_user.id)

    semana_ref = obter_semana_referencia()
    weekly = find_weekly_by_user_sector_semana(
        db, current_user.id, setor_id, semana_ref
    )

    if not weekly:
        # Só cria se estiver dentro da janela de submissão
        validar_janela_submissao(semana_referencia=semana_ref)
        try:
            weekly = criar_weekly_com_rollover(
                db, current_user.id, setor_id, semana_ref
            )
        except IntegrityError:
            # Em requisições concorrentes simultâneas (ex: duas abas), recupera a criada pela outra sessão
            db.rollback()
            weekly = find_weekly_by_user_sector_semana(
                db, current_user.id, setor_id, semana_ref
            )
            if not weekly:
                raise

    return _format_weekly_response(weekly)


def svc_create_weekly(
    body: CreateWeeklyRequest, current_user: User, db: Session
) -> WeeklyResponse:
    """
    Cria explicitamente uma weekly em RASCUNHO para um setor e semana de referência.
    Deve estar dentro da janela de submissão.
    Herda tarefas PENDENTES do membro no setor (Rollover - Fase 4).
    """
    _verificar_vinculo_setor(db, body.setor_id, current_user.id)
    semana_ref = body.semana_referencia or obter_semana_referencia()
    validar_janela_submissao(semana_referencia=semana_ref)

    existente = find_weekly_by_user_sector_semana(
        db, current_user.id, body.setor_id, semana_ref
    )
    if existente:
        raise BadRequestError(
            f"Já existe uma weekly cadastrada para este setor na semana de referência {semana_ref}."
        )

    try:
        weekly_criada = criar_weekly_com_rollover(
            db, current_user.id, body.setor_id, semana_ref
        )
    except IntegrityError:
        db.rollback()
        raise BadRequestError(
            f"Já existe uma weekly cadastrada para este setor na semana de referência {semana_ref}."
        )
    return _format_weekly_response(weekly_criada)


def svc_list_my_weeklies(
    current_user: User,
    db: Session,
    setor_id: UUID | None = None,
    status_filter: str | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> WeeklyListResponse:
    """Lista as weeklies do usuário autenticado com paginação, filtros e contadores."""
    if status_filter and status_filter not in WEEKLY_STATUS_VALIDOS:
        raise BadRequestError(
            f"Status '{status_filter}' inválido. Valores aceitos: {', '.join(sorted(WEEKLY_STATUS_VALIDOS))}."
        )

    if setor_id:
        _verificar_vinculo_setor(db, setor_id, current_user.id)

    weeklies, total = list_weeklies_by_user(
        db, current_user.id, setor_id, status_filter, pagina, limite
    )

    resumos = []
    for w in weeklies:
        total_tasks = len(w.weekly_tasks)
        concluidas = sum(1 for t in w.weekly_tasks if t.concluida)
        impedimentos = sum(1 for t in w.weekly_tasks if t.impedimento)

        resumos.append(
            WeeklySummaryResponse(
                id=w.id,
                usuario_id=w.usuario_id,
                membro_nome=w.usuario.nome_completo if w.usuario else None,
                setor_id=w.setor_id,
                semana_referencia=w.semana_referencia,
                status=w.status,
                enviada_em=w.enviada_em,
                motivo_expiracao=w.motivo_expiracao,
                total_tasks=total_tasks,
                total_concluidas=concluidas,
                total_impedimentos=impedimentos,
                criado_em=w.criado_em,
            )
        )

    return WeeklyListResponse(
        weeklies=resumos,
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_list_sector_weeklies(
    setor_id: UUID,
    status_filter: str | None,
    pagina: int,
    limite: int,
    current_user: User,
    db: Session,
) -> WeeklyListResponse:
    """Lista weeklies de um setor para os líderes ou admin."""
    if not (_is_admin(current_user) or _is_lider_do_setor(db, setor_id, current_user)):
        raise ForbiddenError("Você não tem permissão para visualizar as weeklies deste setor.")

    if status_filter and status_filter not in WEEKLY_STATUS_VALIDOS:
        raise BadRequestError(
            f"Status '{status_filter}' inválido. Valores aceitos: {', '.join(sorted(WEEKLY_STATUS_VALIDOS))}."
        )

    weeklies, total = list_weeklies_by_sector(
        db, setor_id, status_filter, pagina, limite
    )

    resumos = []
    for w in weeklies:
        total_tasks = len(w.weekly_tasks)
        concluidas = sum(1 for t in w.weekly_tasks if t.concluida)
        impedimentos = sum(1 for t in w.weekly_tasks if t.impedimento)

        resumos.append(
            WeeklySummaryResponse(
                id=w.id,
                usuario_id=w.usuario_id,
                membro_nome=w.usuario.nome_completo if w.usuario else None,
                setor_id=w.setor_id,
                semana_referencia=w.semana_referencia,
                status=w.status,
                enviada_em=w.enviada_em,
                motivo_expiracao=w.motivo_expiracao,
                total_tasks=total_tasks,
                total_concluidas=concluidas,
                total_impedimentos=impedimentos,
                criado_em=w.criado_em,
            )
        )

    return WeeklyListResponse(
        weeklies=resumos,
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_get_weekly_detail(
    weekly_id: UUID, current_user: User, db: Session
) -> WeeklyResponse:
    """
    Retorna os detalhes completos de uma weekly.
    Acesso permitido para o próprio dono, líder do setor da weekly ou admin.
    """
    weekly = find_weekly_by_id(db, weekly_id)
    if not weekly:
        raise NotFoundError("Weekly não encontrada.")

    # Permissão: dono ou líder/admin do setor da weekly
    if weekly.usuario_id != current_user.id and not (
        _is_admin(current_user)
        or _is_lider_do_setor(db, weekly.setor_id, current_user)
    ):
        raise ForbiddenError("Você não tem permissão para visualizar esta weekly.")

    return _format_weekly_response(weekly)


def svc_add_task_to_weekly(
    weekly_id: UUID,
    body: AddWeeklyTaskRequest,
    current_user: User,
    db: Session,
) -> WeeklyTaskItemResponse:
    """
    Adiciona uma task à weekly.
    Pode vincular uma task existente (via task_id) ou criar uma nova inline (via titulo).
    Valida que a weekly pertence ao usuário e está dentro da janela de submissão.
    """
    weekly = find_weekly_by_id(db, weekly_id, for_update=True)
    if not weekly:
        raise NotFoundError("Weekly não encontrada.")

    _validar_escrita_weekly(weekly, current_user, db)

    # 1. Obter ou criar a task correspondente
    if body.task_id:
        task = find_task_by_id(db, body.task_id)
        if not task:
            raise NotFoundError("Task informada não encontrada.")

        # Garantia 1: Pertence ao mesmo usuário e mesmo setor da weekly
        if task.usuario_id != current_user.id:
            raise ForbiddenError(
                "Você não pode adicionar tasks de outro usuário à sua weekly."
            )
        if task.setor_id != weekly.setor_id:
            raise BadRequestError(
                "A task informada pertence a um setor diferente desta weekly."
            )
        if task.status != "PENDENTE":
            raise BadRequestError(
                f"Apenas tasks com status 'PENDENTE' podem ser adicionadas à weekly. Status atual: {task.status}."
            )

        # Verificar se já está na weekly
        existente = find_weekly_task(db, weekly.id, task.id)
        if existente:
            raise BadRequestError("Esta task já faz parte desta weekly.")

        proxima_posicao = get_next_weekly_task_posicao(db, weekly.id)
        novo_item = WeeklyTask(
            weekly_id=weekly.id,
            task_id=task.id,
            task=task,
            concluida=False,
            impedimento=None,
            posicao=proxima_posicao,
            origem="NOVA",
        )
        item_criado = add_task_to_weekly(db, novo_item)
        return _format_weekly_task_item(item_criado)
    else:
        # Criação inline de task com garantia de atomicidade
        if body.prazo_conclusao and body.prazo_conclusao < get_now_fortaleza().date():
            raise BadRequestError("O prazo de conclusão não pode ser uma data no passado.")

        prazo = body.prazo_conclusao or (
            get_now_fortaleza().date() + timedelta(days=settings.WEEKLY_TASK_DEFAULT_DEADLINE_DAYS)
        )

        try:
            nova_task = Task(
                usuario_id=current_user.id,
                setor_id=weekly.setor_id,
                titulo=body.titulo.strip(),
                descricao=body.descricao,
                prazo_conclusao=prazo,
            )
            task = create_task(db, nova_task, commit=False)

            proxima_posicao = get_next_weekly_task_posicao(db, weekly.id)
            novo_item = WeeklyTask(
                weekly_id=weekly.id,
                task_id=task.id,
                task=task,
                concluida=False,
                impedimento=None,
                posicao=proxima_posicao,
                origem="NOVA",
            )
            item_criado = add_task_to_weekly(db, novo_item, commit=False)
            db.commit()
            db.refresh(item_criado)
            return _format_weekly_task_item(item_criado)
        except Exception:
            db.rollback()
            raise


def svc_update_weekly_task(
    weekly_id: UUID,
    weekly_task_id: UUID,
    body: UpdateWeeklyTaskRequest,
    current_user: User,
    db: Session,
    background_tasks: BackgroundTasks | None = None,
) -> WeeklyTaskItemResponse:
    """Atualiza status de conclusão e/ou impedimento de uma tarefa na weekly.

    Apenas o proprietário pode alterar, dentro da janela de submissão.
    Se um novo impedimento for registrado, notifica os líderes do setor e administradores.
    """
    weekly = find_weekly_by_id(db, weekly_id, for_update=True)
    if not weekly:
        raise NotFoundError("Weekly não encontrada.")

    _validar_escrita_weekly(weekly, current_user, db)

    weekly_task = find_weekly_task_by_id(db, weekly_task_id, for_update=True)
    if not weekly_task or weekly_task.weekly_id != weekly.id:
        raise NotFoundError("Tarefa não encontrada nesta weekly.")

    if body.concluida is not None:
        weekly_task.concluida = body.concluida

    novo_impedimento_registrado = False
    if "impedimento" in body.model_fields_set:
        antigo_impedimento = weekly_task.impedimento
        novo_valor = body.impedimento.strip() if body.impedimento else None
        weekly_task.impedimento = novo_valor
        if novo_valor and novo_valor != antigo_impedimento:
            novo_impedimento_registrado = True

    commit_changes(db)

    # Disparo de e-mails para líderes do setor e administradores globais
    if novo_impedimento_registrado:
        destinatarios = set()
        for lider in find_sector_leaders(db, weekly.setor_id):
            if lider.email:
                destinatarios.add(lider.email)
        for admin in find_admin_users(db):
            if admin.email:
                destinatarios.add(admin.email)

        destinatarios.discard(current_user.email)

        semana_str = weekly.semana_referencia.strftime("%d/%m/%Y")
        titulo_task = weekly_task.task.titulo if weekly_task.task else "Tarefa"
        setor_nome = weekly.setor.nome if weekly.setor else "Geral"

        for email in destinatarios:
            if background_tasks:
                background_tasks.add_task(
                    enviar_email_impedimento,
                    destinatario=email,
                    titulo_task=titulo_task,
                    nome_membro=current_user.nome_completo,
                    setor_nome=setor_nome,
                    impedimento_texto=weekly_task.impedimento,
                    semana_referencia=semana_str,
                )
            else:
                try:
                    enviar_email_impedimento(
                        destinatario=email,
                        titulo_task=titulo_task,
                        nome_membro=current_user.nome_completo,
                        setor_nome=setor_nome,
                        impedimento_texto=weekly_task.impedimento,
                        semana_referencia=semana_str,
                    )
                except (smtplib.SMTPException, OSError):
                    logger.exception(
                        "❌ Falha ao enviar e-mail de impedimento para %s", email
                    )

    return _format_weekly_task_item(weekly_task)



def svc_remove_task_from_weekly(
    weekly_id: UUID,
    weekly_task_id: UUID,
    current_user: User,
    db: Session,
) -> MensagemResponse:
    """
    Remove uma tarefa da weekly. Apenas o proprietário pode remover dentro da janela,
    e apenas tarefas com origem 'NOVA'.
    Tarefas herdadas de semanas anteriores (origem 'HERDADA') não podem ser removidas pelo membro
    para evitar evasão de tarefas pendentes do relatório (exige ação/intervenção do líder ou admin).
    A task em si é mantida no banco (apenas o vínculo da weekly é deletado).
    Impede remover a última tarefa se a weekly já foi enviada.
    """
    weekly = find_weekly_by_id(db, weekly_id, for_update=True)
    if not weekly:
        raise NotFoundError("Weekly não encontrada.")

    is_lider_ou_admin = _is_admin(current_user) or _is_lider_do_setor(
        db, weekly.setor_id, current_user
    )
    if not is_lider_ou_admin:
        _validar_escrita_weekly(weekly, current_user, db)
    else:
        if weekly.status not in ("RASCUNHO", "REJEITADA"):
            raise BadRequestError(
                f"Não é possível alterar uma weekly com status '{weekly.status}'."
            )

    weekly_task = find_weekly_task_by_id(db, weekly_task_id, for_update=True)
    if not weekly_task or weekly_task.weekly_id != weekly.id:
        raise NotFoundError("Tarefa não encontrada nesta weekly.")

    # Regra de auditoria e integridade: membro comum não pode remover tarefa herdada de rollover
    if weekly_task.origem == "HERDADA" and not is_lider_ou_admin:
        raise ForbiddenError(
            "Tarefas herdadas de semanas anteriores não podem ser removidas do relatório pelo membro. "
            "Apenas o líder do setor ou administrador pode removê-las."
        )

    # Se a weekly está REJEITADA, ela é um relatório submetido devolvido para correções.
    # Não pode ter sua última tarefa removida, ficando vazia.
    if weekly.status == "REJEITADA":
        total_tarefas = (
            db.query(WeeklyTask)
            .filter(WeeklyTask.weekly_id == weekly.id)
            .count()
        )
        if total_tarefas <= 1:
            raise BadRequestError(
                "Não é possível remover a última tarefa de uma weekly rejeitada. "
                "O relatório deve conter pelo menos uma tarefa."
            )

    remove_task_from_weekly(db, weekly_task)
    return MensagemResponse(mensagem="Tarefa removida da weekly com sucesso.")


def svc_send_weekly(
    weekly_id: UUID, current_user: User, db: Session
) -> WeeklyResponse:
    """
    Transita a weekly de RASCUNHO para ENVIADA.
    Apenas o proprietário da weekly pode enviá-la, e somente dentro da janela de submissão.
    """
    weekly = find_weekly_by_id(db, weekly_id, for_update=True)
    if not weekly:
        raise NotFoundError("Weekly não encontrada.")

    if weekly.status == "ENVIADA":
        raise BadRequestError("Esta weekly já foi enviada.")

    _validar_escrita_weekly(weekly, current_user, db)

    total_tarefas = (
        db.query(WeeklyTask)
        .filter(WeeklyTask.weekly_id == weekly.id)
        .count()
    )
    if total_tarefas == 0:
        raise BadRequestError(
            "A weekly deve conter pelo menos uma tarefa antes de ser enviada."
        )

    weekly.status = "ENVIADA"
    weekly.enviada_em = get_now_fortaleza().astimezone(timezone.utc)
    weekly.avaliada_em = None
    weekly.avaliada_por = None
    weekly.observacao_lider = None

    # Congela snapshot dos campos históricos das tarefas na submissão
    for weekly_task in weekly.weekly_tasks:
        if weekly_task.task:
            weekly_task.snapshot_titulo = weekly_task.task.titulo
            weekly_task.snapshot_descricao = weekly_task.task.descricao
            weekly_task.snapshot_prazo_conclusao = weekly_task.task.prazo_conclusao

    commit_changes(db)

    return _format_weekly_response(weekly)


def svc_reabrir_weekly(
    weekly_id: UUID, current_user: User, db: Session
) -> WeeklyResponse:
    """
    Transita uma weekly de ENVIADA de volta para RASCUNHO para permitir ajustes pelo autor,
    desde que a janela de submissão ainda esteja aberta e a weekly não tenha sido aprovada.
    """
    weekly = find_weekly_by_id(db, weekly_id, for_update=True)
    if not weekly:
        raise NotFoundError("Weekly não encontrada.")

    _verificar_proprietario_weekly(weekly, current_user)
    _verificar_vinculo_setor(db, weekly.setor_id, current_user.id)
    validar_janela_submissao(semana_referencia=weekly.semana_referencia)

    if weekly.status == "APROVADA":
        raise BadRequestError("Não é possível reabrir uma weekly já aprovada.")

    if weekly.status != "ENVIADA":
        raise BadRequestError(
            f"Apenas weeklies com status 'ENVIADA' podem ser reabertas. Status atual: {weekly.status}."
        )

    weekly.status = "RASCUNHO"
    weekly.enviada_em = None
    for weekly_task in weekly.weekly_tasks:
        weekly_task.snapshot_titulo = None
        weekly_task.snapshot_descricao = None
        weekly_task.snapshot_prazo_conclusao = None
    commit_changes(db)

    return _format_weekly_response(weekly)


def svc_evaluate_weekly(
    weekly_id: UUID,
    body: EvaluateWeeklyRequest,
    current_user: User,
    db: Session,
) -> WeeklyResponse:
    """
    Avalia uma weekly (aprova ou rejeita).
    Apenas líderes do setor ou admin.
    Quando APROVADA, consolida a conclusão das tarefas marcadas como concluídas (Task.status = CONCLUIDA).
    """
    weekly = find_weekly_by_id(db, weekly_id, for_update=True)
    if not weekly:
        raise NotFoundError("Weekly não encontrada.")

    # 1. Bloqueio de auto-avaliação (ninguém avalia a própria weekly)
    if weekly.usuario_id == current_user.id:
        raise ForbiddenError("Você não pode avaliar a sua própria weekly.")

    # 2. Permissão básica: deve ser líder do setor ou admin/super_admin global
    if not (_is_admin(current_user) or _is_lider_do_setor(db, weekly.setor_id, current_user)):
        raise ForbiddenError("Você não tem permissão para avaliar esta weekly.")

    # 3. Hierarquia de Governança: weeklies de líderes ou administradores só podem ser avaliadas por administradores
    autor_is_lider = _is_lider_do_setor(db, weekly.setor_id, weekly.usuario)
    if (autor_is_lider or _is_admin(weekly.usuario)) and not _is_admin(current_user):
        raise ForbiddenError(
            "Weeklies de líderes só podem ser avaliadas por administradores."
        )

    if weekly.status not in ("ENVIADA", "REJEITADA"):
        raise BadRequestError(
            f"Apenas weeklies ENVIADAS ou REJEITADAS podem ser avaliadas. Status atual: {weekly.status}."
        )

    if body.status not in ("APROVADA", "REJEITADA"):
        raise BadRequestError(
            f"Status '{body.status}' inválido para avaliação. Permitidos: APROVADA, REJEITADA."
        )

    obs_limpa = body.observacao_lider.strip() if body.observacao_lider else None
    if body.status == "REJEITADA":
        if not obs_limpa:
            raise BadRequestError(
                "É obrigatório informar uma observação (feedback) não vazia ao rejeitar a weekly."
            )
        agora = get_now_fortaleza()
        # Prazo limite para o líder rejeitar: Quarta-feira às 23:59:59 da semana de referência
        quarta_data = weekly.semana_referencia + timedelta(days=2)
        quarta_limite = datetime(
            quarta_data.year, quarta_data.month, quarta_data.day, 23, 59, 59, tzinfo=FUSO_LLAB
        )
        if agora > quarta_limite:
            raise BadRequestError(
                "O prazo para rejeitar relatórios desta semana encerrou na quarta-feira às 23:59. "
                "O relatório só pode ser aprovado."
            )

    if body.status == "APROVADA":
        total_tarefas = (
            db.query(WeeklyTask)
            .filter(WeeklyTask.weekly_id == weekly.id)
            .count()
        )
        if total_tarefas == 0:
            raise BadRequestError(
                "Não é possível aprovar uma weekly que não contém nenhuma tarefa."
            )

    try:
        weekly.status = body.status
        weekly.observacao_lider = obs_limpa
        weekly.avaliada_em = get_now_fortaleza().astimezone(timezone.utc)
        weekly.avaliada_por = current_user.id

        # Consolidação e garantia de snapshot quando a weekly é APROVADA
        if body.status == "APROVADA":
            for weekly_task in weekly.weekly_tasks:
                if weekly_task.task:
                    if weekly_task.snapshot_titulo is None:
                        weekly_task.snapshot_titulo = weekly_task.task.titulo
                    if weekly_task.snapshot_descricao is None:
                        weekly_task.snapshot_descricao = weekly_task.task.descricao
                    if weekly_task.snapshot_prazo_conclusao is None:
                        weekly_task.snapshot_prazo_conclusao = weekly_task.task.prazo_conclusao

            concluidas_task_ids = [
                weekly_task.task_id
                for weekly_task in weekly.weekly_tasks
                if weekly_task.concluida and weekly_task.task_id
            ]
            if concluidas_task_ids:
                # Atualização atômica e condicional no banco de dados:
                # Apenas tasks que AINDA estão 'PENDENTE' no momento do commit são consolidadas como 'CONCLUIDA'.
                # Tarefas soft-deleted ('REMOVIDA_PELO_LIDER') ou em auditoria ('EM_AUDITORIA')
                # NÃO serão sobrescritas acidentalmente.
                db.query(Task).filter(
                    Task.id.in_(concluidas_task_ids),
                    Task.status == "PENDENTE",
                ).update({Task.status: "CONCLUIDA"}, synchronize_session="fetch")

        commit_changes(db)
    except Exception:
        db.rollback()
        raise

    return _format_weekly_response(weekly)


# ── Sistema de Advertências (Fase 7) ──────────────────────────


def _format_warning_response(w: WeeklyWarning) -> WeeklyWarningResponse:
    """Projeta o modelo ORM WeeklyWarning no schema de resposta Pydantic."""
    return WeeklyWarningResponse(
        id=w.id,
        usuario_id=w.usuario_id,
        usuario_nome=w.usuario.nome_completo if w.usuario else None,
        setor_id=w.setor_id,
        setor_nome=w.setor.nome if w.setor else None,
        tipo=w.tipo,
        semana_referencia=w.semana_referencia,
        semanas_ausentes=w.semanas_ausentes,
        criado_em=w.criado_em,
    )


def calcular_primeira_semana_obrigatoria(data_inicio: date) -> date:
    """Retorna a primeira segunda-feira de referência em que a entrega é exigível.

    - Se a data de início coincidir com uma Segunda-feira (0), a janela fechou/fecha
      nesta própria data, configurando o primeiro ciclo exigível.
    - Para qualquer outro dia da semana (Terça a Domingo), a primeira segunda-feira
      exigível é a próxima segunda-feira:
      * Terça (1) a Quinta (3): a janela da semana anterior já fechou antes do início da
        obrigação. Portanto, a primeira semana exigível será a da próxima segunda-feira.
      * Sexta (4) a Domingo (6): a janela para a segunda-feira que vem abriu na sexta-feira.
        Logo, a primeira entrega exigível é a dessa segunda-feira.
    """
    dia_semana = data_inicio.weekday()
    if dia_semana == 0:
        return data_inicio
    return data_inicio + timedelta(days=7 - dia_semana)


def calcular_inicio_obrigacao_setor(
    assoc: SectorUser,
    marco_implantacao: date | None = None,
) -> date:
    """Calcula a data a partir da qual o membro passou a ter a obrigação de entregar weeklies no setor.

    Considera o momento mais recente (max) entre:
    1. Data de ingresso geral do usuário na organização (usuario.data_ingresso);
    2. Data de ingresso ou criação do vínculo neste setor específico (assoc.data_ingresso ou assoc.criado_em);
    3. Marco de implantação oficial do módulo de weeklies (settings.WEEKLY_MARCO_IMPLANTACAO).
    """
    datas: list[date] = []

    # 1. Ingresso geral do usuário
    if assoc.usuario and assoc.usuario.data_ingresso:
        datas.append(assoc.usuario.data_ingresso)

    # 2. Vínculo específico com o setor
    if assoc.data_ingresso:
        datas.append(assoc.data_ingresso)
    elif assoc.criado_em:
        dt = (
            assoc.criado_em
            if assoc.criado_em.tzinfo
            else assoc.criado_em.replace(tzinfo=timezone.utc)
        )
        datas.append(dt.astimezone(FUSO_LLAB).date())

    # 3. Marco de implantação do módulo
    if marco_implantacao is None:
        marco_implantacao = settings.WEEKLY_MARCO_IMPLANTACAO
    if marco_implantacao:
        datas.append(marco_implantacao)

    if not datas:
        return get_now_fortaleza().date()

    return max(datas)


def contar_semanas_consecutivas_sem_envio(
    db: Session,
    usuario_id: UUID,
    setor_id: UUID,
    semana_base: date,
    data_ingresso: date | None = None,
    data_inicio_obrigacao: date | None = None,
) -> int:
    """Conta quantas semanas consecutivas, a partir de semana_base (inclusive) e retrocedendo,
    o membro não enviou a weekly no setor (ou seja, não possui weekly ou ela permaneceu em RASCUNHO).
    Interrompe a contagem assim que encontrar uma weekly enviada/avaliada/expirada ou atingir
    data anterior ao início da obrigação naquele setor.
    """
    limite_inicio = data_inicio_obrigacao or data_ingresso
    primeira_semana_valida = (
        calcular_primeira_semana_obrigatoria(limite_inicio)
        if limite_inicio
        else None
    )

    consecutivas = 0
    semana_cursor = semana_base

    for _ in range(12):  # Limite máximo razoável de retrocesso
        if primeira_semana_valida and semana_cursor < primeira_semana_valida:
            break

        weekly = find_weekly_by_user_sector_semana(
            db, usuario_id, setor_id, semana_cursor
        )
        if weekly and (
            weekly.status in ("ENVIADA", "APROVADA", "REJEITADA")
            or weekly.status == "EXPIRADA"
        ):
            # O membro enviou nesta semana: interrompe a sequência consecutiva de ausências
            break

        consecutivas += 1
        semana_cursor -= timedelta(days=7)

    return consecutivas


def svc_processar_advertencias_ausencias(
    db: Session, semana_referencia: date | None = None
) -> dict:
    """Processa ausências de submissão da semana_referencia (após fechamento da janela).

    Gera advertências automáticas para membros que acumularam ausências consecutivas:
    - 2 semanas consecutivas: 1a_ADVERTENCIA
    - 3 semanas consecutivas: 2a_ADVERTENCIA
    - 4+ semanas consecutivas: DESLIGAMENTO
    Envia e-mails de alerta e retorna sumário da execução.
    """
    if semana_referencia is None:
        semana_referencia = obter_semana_referencia()

    membros_setores = find_active_sector_members(db)
    advertencias_geradas = []
    detalhes_ausentes = []
    total_ausentes = 0
    total_enviadas = 0

    for assoc in membros_setores:
        # Início da obrigação do membro neste setor específico:
        data_inicio = calcular_inicio_obrigacao_setor(
            assoc, marco_implantacao=settings.WEEKLY_MARCO_IMPLANTACAO
        )
        primeira_semana = calcular_primeira_semana_obrigatoria(data_inicio)

        # Se a semana avaliada é anterior ao início da obrigação do membro no setor,
        # o membro não tinha o dever de submeter weekly nesta semana (ex: recém-ingressado).
        if semana_referencia < primeira_semana:
            continue

        weekly = find_weekly_by_user_sector_semana(
            db, assoc.usuario_id, assoc.setor_id, semana_referencia
        )
        if weekly and (
            weekly.status in ("ENVIADA", "APROVADA", "REJEITADA")
            or weekly.status == "EXPIRADA"
        ):
            total_enviadas += 1
            continue

        total_ausentes += 1
        detalhes_ausentes.append(
            {
                "usuario_id": str(assoc.usuario_id),
                "setor_id": str(assoc.setor_id),
                "status_weekly": weekly.status if weekly else "NAO_CRIADA",
            }
        )

        semanas_sem_envio = contar_semanas_consecutivas_sem_envio(
            db,
            assoc.usuario_id,
            assoc.setor_id,
            semana_referencia,
            data_inicio_obrigacao=data_inicio,
        )

        tipo: str | None = None
        if semanas_sem_envio == settings.WEEKLY_STRIKE_1_WEEKS:
            tipo = "1a_ADVERTENCIA"
        elif semanas_sem_envio == settings.WEEKLY_STRIKE_2_WEEKS:
            tipo = "2a_ADVERTENCIA"
        elif semanas_sem_envio >= settings.WEEKLY_STRIKE_3_WEEKS:
            tipo = "DESLIGAMENTO"

        if tipo:
            existente = find_warning_by_user_sector_semana(
                db, assoc.usuario_id, assoc.setor_id, semana_referencia
            )
            if not existente:
                nova_adv = WeeklyWarning(
                    usuario_id=assoc.usuario_id,
                    setor_id=assoc.setor_id,
                    tipo=tipo,
                    semana_referencia=semana_referencia,
                    semanas_ausentes=semanas_sem_envio,
                )
                try:
                    with db.begin_nested():
                        db.add(nova_adv)
                        db.flush()
                    db.commit()
                except IntegrityError:
                    # Concorrência detectada: outra réplica/worker inseriu a advertência milissegundos antes
                    logger.info(
                        "Advertência já gerada concorrentemente para usuário %s no setor %s (semana %s). Ignorando.",
                        assoc.usuario_id,
                        assoc.setor_id,
                        semana_referencia,
                    )
                    continue

                advertencias_geradas.append(
                    {
                        "usuario_id": str(assoc.usuario_id),
                        "setor_id": str(assoc.setor_id),
                        "tipo": tipo,
                        "semanas_ausentes": semanas_sem_envio,
                    }
                )

                # Notificação por e-mail apenas para a transação vencedora
                if assoc.usuario and assoc.usuario.email:
                    try:
                        enviar_email_advertencia(
                            destinatario=assoc.usuario.email,
                            nome_membro=assoc.usuario.nome_completo,
                            tipo=tipo,
                            semanas_ausentes=semanas_sem_envio,
                            setor_nome=assoc.setor.nome if assoc.setor else "Geral",
                            semana_referencia=semana_referencia.strftime("%d/%m/%Y"),
                        )
                    except (smtplib.SMTPException, OSError):
                        logger.exception(
                            "❌ Falha ao enviar e-mail de advertência para %s",
                            assoc.usuario.email,
                        )

    return {
        "semana_referencia": str(semana_referencia),
        "total_membros": len(membros_setores),
        "enviadas": total_enviadas,
        "ausencias": total_ausentes,
        "detalhes_ausentes": detalhes_ausentes,
        "advertencias_geradas": len(advertencias_geradas),
        "detalhes": advertencias_geradas,
    }


def svc_list_sector_warnings(
    setor_id: UUID,
    current_user: User,
    db: Session,
    pagina: int = 1,
    limite: int = 20,
) -> WeeklyWarningListResponse:
    """Lista as advertências de um setor. Apenas líderes do setor ou admin/super_admin."""
    if not (_is_admin(current_user) or _is_lider_do_setor(db, setor_id, current_user)):
        raise ForbiddenError(
            "Você não tem permissão para visualizar as advertências deste setor."
        )

    warnings, total = list_warnings_by_sector(db, setor_id, pagina, limite)
    return WeeklyWarningListResponse(
        advertencias=[_format_warning_response(w) for w in warnings],
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_list_my_warnings(
    current_user: User,
    db: Session,
    setor_id: UUID | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> WeeklyWarningListResponse:
    """Lista as advertências emitidas para o usuário autenticado."""
    if setor_id:
        _verificar_vinculo_setor(db, setor_id, current_user.id)

    warnings, total = list_warnings_by_user(
        db, current_user.id, setor_id, pagina, limite
    )
    return WeeklyWarningListResponse(
        advertencias=[_format_warning_response(w) for w in warnings],
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_processar_expiracao_weeklies(
    db: Session, semana_referencia: date | None = None
) -> dict:
    """
    Varredura que expira weeklies não finalizadas de semanas cujo ciclo já avançou.
    - Weeklies em ENVIADA que não foram avaliadas pelo líder até o fechamento (Quinta 23:59 / Sexta 00h)
      transicionam para EXPIRADA (motivo: OMISSAO_LIDERANCA).
    - Weeklies em REJEITADA cujo prazo de carência de 24h expirou sem novo envio
      transicionam para EXPIRADA (motivo: CORRECAO_NAO_ENVIADA).
    """
    if semana_referencia is None:
        semana_referencia = obter_semana_referencia()

    query = db.query(Weekly).filter(
        Weekly.status.in_(["ENVIADA", "REJEITADA"]),
    )
    if semana_referencia is not None:
        query = query.filter(Weekly.semana_referencia <= semana_referencia)
    candidatas = query.all()

    agora = get_now_fortaleza()
    expiradas_lider = 0
    expiradas_membro = 0

    for w in candidatas:
        w_quinta_data = w.semana_referencia + timedelta(days=3)
        quinta_limite = datetime(
            w_quinta_data.year,
            w_quinta_data.month,
            w_quinta_data.day,
            23,
            59,
            59,
            tzinfo=FUSO_LLAB,
        )

        if w.status == "ENVIADA" and agora > quinta_limite:
            setor_nome = w.setor.nome if w.setor else "Geral"
            detalhe = (
                f"A liderança do setor {setor_nome} não avaliou o relatório até o fechamento do ciclo."
            )
            # Atualização atômica condicional: protege contra aprovação/rejeição concorrente
            afetados = (
                db.query(Weekly)
                .filter(
                    Weekly.id == w.id,
                    Weekly.status == "ENVIADA",
                )
                .update(
                    {
                        Weekly.status: "EXPIRADA",
                        Weekly.motivo_expiracao: "OMISSAO_LIDERANCA",
                        Weekly.detalhe_expiracao: detalhe,
                    },
                    synchronize_session=False,
                )
            )
            if afetados:
                expiradas_lider += 1

        elif w.status == "REJEITADA":
            avaliada_tz = (
                w.avaliada_em
                if (w.avaliada_em and w.avaliada_em.tzinfo)
                else (w.avaliada_em.replace(tzinfo=timezone.utc) if w.avaliada_em else None)
            )
            limite_carencia = (
                avaliada_tz.astimezone(FUSO_LLAB) + timedelta(hours=24)
                if avaliada_tz
                else quinta_limite
            )
            if agora > limite_carencia:
                membro_nome = w.usuario.nome_completo if w.usuario else "Membro"
                detalhe = (
                    f"O membro {membro_nome} não reenviou as correções no prazo de carência de 24h."
                )
                # Atualização atômica condicional: protege contra reenvio concorrente
                afetados = (
                    db.query(Weekly)
                    .filter(
                        Weekly.id == w.id,
                        Weekly.status == "REJEITADA",
                    )
                    .update(
                        {
                            Weekly.status: "EXPIRADA",
                            Weekly.motivo_expiracao: "CORRECAO_NAO_ENVIADA",
                            Weekly.detalhe_expiracao: detalhe,
                        },
                        synchronize_session=False,
                    )
                )
                if afetados:
                    expiradas_membro += 1

    commit_changes(db)
    db.expire_all()

    return {
        "semana_referencia": str(semana_referencia),
        "total_expiradas": expiradas_lider + expiradas_membro,
        "expiradas_omissao_lideranca": expiradas_lider,
        "expiradas_correcao_membro": expiradas_membro,
    }


# ── Auditoria de Tasks (Fase 8) ──────────────────────────────


def svc_processar_auditoria_tasks(
    db: Session, momento: datetime | None = None
) -> dict:
    """Verifica tarefas pendentes que estouraram o prazo de conclusão e as transfere para EM_AUDITORIA.

    Além disso, identifica tarefas sob auditoria há >= 7 dias sem ação da liderança e as escala para os admins.
    """
    if momento is None:
        momento = get_now_fortaleza()

    hoje = momento.date()
    agora_utc = momento.astimezone(timezone.utc)

    # 1. Identificar tarefas pendentes vencidas
    tasks_vencidas = find_expired_pending_tasks(db, hoje)
    novas_em_auditoria = []

    for task in tasks_vencidas:
        # Atualização atômica condicional: só transiciona se ainda for PENDENTE e vencida no banco
        afetados = (
            db.query(Task)
            .filter(
                Task.id == task.id,
                Task.status == "PENDENTE",
                Task.prazo_conclusao < hoje,
            )
            .update(
                {
                    Task.status: "EM_AUDITORIA",
                    Task.entrada_auditoria_em: agora_utc,
                },
                synchronize_session=False,
            )
        )
        if afetados:
            novas_em_auditoria.append(task)

    # Persiste imediatamente as transições antes de iniciar o envio de e-mails (evita transações longas abertas durante SMTP)
    commit_changes(db)
    db.expire_all()

    # Dispara e-mails apenas para as tarefas que efetivamente transicionaram para auditoria
    for task in novas_em_auditoria:
        # Destinatários: líderes do setor + admins globais
        destinatarios = set()
        lideres = find_sector_leaders(db, task.setor_id)
        for l in lideres:
            if l.email:
                destinatarios.add(l.email)
        admins = find_admin_users(db)
        for a in admins:
            if a.email:
                destinatarios.add(a.email)

        prazo_str = (
            task.prazo_conclusao.strftime("%d/%m/%Y")
            if task.prazo_conclusao
            else "Sem data"
        )
        for email in destinatarios:
            try:
                enviar_email_task_auditoria(
                    destinatario=email,
                    titulo_task=task.titulo,
                    nome_membro=task.usuario.nome_completo if task.usuario else "Membro",
                    setor_nome=task.setor.nome if task.setor else "Geral",
                    prazo_conclusao=prazo_str,
                )
            except (smtplib.SMTPException, OSError):
                logger.exception(
                    "❌ Falha ao enviar e-mail de auditoria da task %s para %s",
                    task.id,
                    email,
                )

    # 2. Escalonamento: tasks em auditoria há mais de 7 dias sem ação
    tasks_em_auditoria, _ = find_tasks_in_audit(db, limite=1000)
    tasks_escaladas = []

    for task in tasks_em_auditoria:
        data_base_auditoria = (
            task.entrada_auditoria_em.date()
            if task.entrada_auditoria_em
            else task.criado_em.date()
        )
        dias_auditoria = (hoje - data_base_auditoria).days

        if dias_auditoria >= settings.WEEKLY_AUDIT_ESCALATION_DAYS:
            tasks_escaladas.append((task, dias_auditoria))
            admins = find_admin_users(db)
            for a in admins:
                if a.email:
                    try:
                        enviar_email_escalonamento_auditoria(
                            destinatario=a.email,
                            titulo_task=task.titulo,
                            nome_membro=task.usuario.nome_completo if task.usuario else "Membro",
                            setor_nome=task.setor.nome if task.setor else "Geral",
                            dias_em_auditoria=dias_auditoria,
                        )
                    except (smtplib.SMTPException, OSError):
                        logger.exception(
                            "❌ Falha ao enviar e-mail de escalonamento da task %s para %s",
                            task.id,
                            a.email,
                        )

    commit_changes(db)

    return {
        "data_processamento": str(hoje),
        "novas_em_auditoria": len(novas_em_auditoria),
        "escaladas_admin": len(tasks_escaladas),
        "detalhes_novas": [
            {"id": str(t.id), "titulo": t.titulo} for t in novas_em_auditoria
        ],
        "detalhes_escaladas": [
            {"id": str(t.id), "titulo": t.titulo, "dias": d}
            for t, d in tasks_escaladas
        ],
    }


def svc_list_sector_tasks_in_audit(
    setor_id: UUID,
    current_user: User,
    db: Session,
    pagina: int = 1,
    limite: int = 20,
) -> TaskListResponse:
    """Lista as tarefas em status EM_AUDITORIA de um setor. Permitido para líderes do setor ou admin/super_admin."""
    if not (_is_admin(current_user) or _is_lider_do_setor(db, setor_id, current_user)):
        raise ForbiddenError(
            "Você não tem permissão para visualizar tarefas em auditoria deste setor."
        )

    tasks, total = find_tasks_in_audit(
        db, setor_id=setor_id, pagina=pagina, limite=limite
    )
    return TaskListResponse(
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_concluir_task_auditoria(
    task_id: UUID,
    current_user: User,
    db: Session,
) -> TaskResponse:
    """Conclui uma tarefa que está sob auditoria (ou pendente). Apenas líderes do setor ou admin/super_admin."""
    task = find_task_by_id(db, task_id)
    if not task:
        raise NotFoundError("Task não encontrada.")

    if not (_is_admin(current_user) or _is_lider_do_setor(db, task.setor_id, current_user)):
        raise ForbiddenError(
            "Apenas o líder do setor ou admin pode concluir tarefas em auditoria."
        )

    # Bloqueio de auto-auditoria: ninguém conclui a própria tarefa em auditoria
    if task.usuario_id == current_user.id:
        raise ForbiddenError("Você não pode concluir a sua própria tarefa em auditoria.")

    # Hierarquia de governança: tarefas de líderes em auditoria só podem ser concluídas por administradores
    if _is_lider_do_setor(db, task.setor_id, task.usuario) and not _is_admin(current_user):
        raise ForbiddenError(
            "Tarefas de líderes em auditoria só podem ser concluídas por administradores."
        )

    if task.status not in ("EM_AUDITORIA", "PENDENTE"):
        raise BadRequestError(
            f"Apenas tasks com status 'EM_AUDITORIA' ou 'PENDENTE' podem ser concluídas por esta rota. Status atual: {task.status}."
        )

    task.status = "CONCLUIDA"
    task.entrada_auditoria_em = None
    update_task(db)

    return TaskResponse.model_validate(task)


# ── Atribuição de Tasks (Fase 9) ─────────────────────────────


def _format_assignment_response(a: TaskAssignment) -> TaskAssignmentResponse:
    """Formata o modelo ORM TaskAssignment para o schema público de resposta."""
    return TaskAssignmentResponse(
        id=a.id,
        task_id=a.task_id,
        task_titulo=a.task.titulo if a.task else None,
        solicitante_id=a.solicitante_id,
        solicitante_nome=a.solicitante.nome_completo if a.solicitante else None,
        atribuido_id=a.atribuido_id,
        atribuido_nome=a.atribuido.nome_completo if a.atribuido else None,
        status=a.status,
        criado_em=a.criado_em,
        respondido_em=a.respondido_em,
    )


def svc_create_task_assignment(
    task_id: UUID,
    body: CreateTaskAssignmentRequest,
    current_user: User,
    db: Session,
) -> TaskAssignmentResponse:
    """Envia um convite de colaboração em uma task para outro membro do mesmo setor.

    O solicitante deve ser o proprietário da tarefa ou líder/admin do setor.
    A tarefa deve estar PENDENTE e o convidado deve estar vinculado ao setor.
    """
    task = find_task_by_id(db, task_id, for_update=True)
    if not task:
        raise NotFoundError("Task não encontrada.")

    if task.status != "PENDENTE":
        raise BadRequestError(
            f"Apenas tarefas com status 'PENDENTE' podem ser atribuídas. Status atual: {task.status}."
        )

    # Impede delegação em cascata: tarefas que já são cópias clonadas não podem originar novos convites
    if task.origem_task_id is not None:
        raise BadRequestError(
            "Não é permitido atribuir tarefas clonadas. Apenas a tarefa original pode originar convites de colaboração."
        )

    # 1. Autorização do Solicitante:
    # Solicitante deve possuir vínculo ativo com o setor da tarefa (a menos que seja admin global)
    if not _is_admin(current_user):
        _verificar_vinculo_setor(db, task.setor_id, current_user.id)

    # Se não for o dono da tarefa, deve ser líder do setor ou admin global
    if task.usuario_id != current_user.id and not (
        _is_admin(current_user)
        or _is_lider_do_setor(db, task.setor_id, current_user)
    ):
        raise ForbiddenError("Você não tem permissão para atribuir esta tarefa.")

    if body.atribuido_id == current_user.id:
        raise BadRequestError("Não é possível atribuir uma tarefa a si mesmo.")

    if body.atribuido_id == task.usuario_id:
        raise BadRequestError("A tarefa já pertence a este membro.")

    # 2. Elegibilidade do Destinatário:
    atribuido = db.query(User).filter(User.id == body.atribuido_id).first()
    if not atribuido or atribuido.status_id != StatusID.ATIVO:
        raise NotFoundError("Usuário a ser atribuído não foi encontrado ou está inativo.")

    # Impede atribuição a administradores e super administradores
    if _is_admin(atribuido):
        raise ForbiddenError("Não é permitido atribuir tarefas a administradores ou super administradores.")

    # Convidado deve possuir vínculo ativo com ao menos um setor no sistema
    vinculo_destinatario = (
        db.query(SectorUser)
        .filter(SectorUser.usuario_id == atribuido.id)
        .first()
    )
    if not vinculo_destinatario:
        raise ForbiddenError("O usuário convidado não possui vínculo com nenhum setor.")

    # Impede convites pendentes duplicados para o mesmo membro e tarefa
    pendente = find_pending_assignment_by_task_and_user(
        db, task.id, body.atribuido_id
    )
    if pendente:
        raise ConflictError(
            "Já existe um convite pendente para este membro nesta tarefa."
        )

    # Impede convite se o membro já possui uma cópia clonada desta tarefa
    ja_possui_copia = (
        db.query(Task)
        .filter(
            Task.usuario_id == body.atribuido_id,
            Task.origem_task_id == task.id,
        )
        .first()
    )
    if ja_possui_copia:
        raise ConflictError(
            "Este membro já possui uma cópia desta tarefa atribuída."
        )

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=current_user.id,
        atribuido_id=body.atribuido_id,
        status="PENDENTE",
    )
    create_task_assignment(db, assignment, commit=True)

    # Dispara e-mail de convite
    atribuido = db.query(User).filter(User.id == body.atribuido_id).first()
    if atribuido and atribuido.email:
        prazo_str = (
            task.prazo_conclusao.strftime("%d/%m/%Y")
            if task.prazo_conclusao
            else "A definir"
        )
        try:
            enviar_email_convite_task(
                destinatario=atribuido.email,
                titulo_task=task.titulo,
                nome_solicitante=current_user.nome_completo,
                nome_atribuido=atribuido.nome_completo,
                setor_nome=task.setor.nome if task.setor else "Geral",
                prazo_conclusao=prazo_str,
            )
        except (smtplib.SMTPException, OSError):
            logger.exception(
                "❌ Falha ao enviar e-mail de convite da task %s", task.id
            )

    return _format_assignment_response(assignment)


def svc_respond_task_assignment(
    assignment_id: UUID,
    aceitar: bool,
    current_user: User,
    db: Session,
) -> TaskAssignmentResponse:
    """Responde a um convite de tarefa (ACEITAR ou RECUSAR).

    Ao aceitar:
    - Revalida elegibilidade do destinatário (vínculo com o setor, cargo) e da tarefa (status PENDENTE).
    - O status do convite muda para 'ACEITA'.
    - Uma nova tarefa independente é clonada para o membro convidado com origem_task_id apontando para a original.
    - Se a janela de submissão estiver aberta e o membro possuir uma weekly em RASCUNHO na semana atual, a tarefa clonada é vinculada a ela.
    - O solicitante recebe um e-mail de confirmação.

    Ao recusar:
    - O status muda para 'RECUSADA' e o solicitante é notificado.
    """
    # 1. Lock exclusivo no convite para serializar respostas concorrentes
    assignment = find_assignment_by_id(db, assignment_id, for_update=True)
    if not assignment:
        raise NotFoundError("Convite de tarefa não encontrado.")

    if assignment.atribuido_id != current_user.id:
        raise ForbiddenError(
            "Você não tem permissão para responder a este convite."
        )

    if assignment.status != "PENDENTE":
        raise BadRequestError(
            f"Este convite já foi respondido ou não está mais pendente (status atual: {assignment.status})."
        )

    task_orig = assignment.task
    if not task_orig:
        raise NotFoundError(
            "Tarefa de origem associada ao convite não foi encontrada."
        )

    agora_utc = get_now_fortaleza().astimezone(timezone.utc)

    if aceitar:
        # 2. Revalidação do status da tarefa de origem
        if task_orig.status != "PENDENTE":
            assignment.status = "EXPIRADA"
            assignment.respondido_em = agora_utc
            commit_changes(db)
            raise BadRequestError(
                f"A tarefa original não está mais disponível para colaboração (status atual: '{task_orig.status}')."
            )

        # 3. Revalidação do cargo do destinatário (não pode ser admin/super_admin)
        if _is_admin(current_user):
            assignment.status = "EXPIRADA"
            assignment.respondido_em = agora_utc
            commit_changes(db)
            raise ForbiddenError(
                "Administradores não podem receber atribuições de tarefas."
            )

        # 4. Determinação do setor da cópia e revalidação do vínculo do destinatário
        # Se o convidado pertencer ao mesmo setor da tarefa original, utiliza o setor original.
        # Caso pertença a outro setor (colaboração intersetorial), a cópia é registrada
        # e administrada no setor de origem do próprio convidado.
        assoc_mesmo_setor = find_sector_user(
            db, task_orig.setor_id, current_user.id
        )
        if assoc_mesmo_setor:
            setor_destino_id = task_orig.setor_id
        else:
            vinculo_proprio_setor = (
                db.query(SectorUser)
                .filter(SectorUser.usuario_id == current_user.id)
                .order_by(SectorUser.id.asc())
                .first()
            )
            if not vinculo_proprio_setor:
                assignment.status = "EXPIRADA"
                assignment.respondido_em = agora_utc
                commit_changes(db)
                raise ForbiddenError(
                    "Você não possui vínculo ativo com nenhum setor para receber esta tarefa."
                )
            setor_destino_id = vinculo_proprio_setor.setor_id

        # 5. Transição atômica condicional de status: apenas quem encontrar PENDENTE avança
        rows_updated = (
            db.query(TaskAssignment)
            .filter(
                TaskAssignment.id == assignment.id,
                TaskAssignment.status == "PENDENTE",
            )
            .update(
                {
                    TaskAssignment.status: "ACEITA",
                    TaskAssignment.respondido_em: agora_utc,
                },
                synchronize_session="fetch",
            )
        )
        if rows_updated == 0:
            raise BadRequestError(
                "Este convite já foi respondido ou não está mais pendente."
            )

        # 6. Verificação de segurança adicional para evitar duplicidade de cópia
        ja_clonada = (
            db.query(Task)
            .filter(
                Task.usuario_id == assignment.atribuido_id,
                Task.origem_task_id == task_orig.id,
            )
            .first()
        )
        if ja_clonada:
            raise ConflictError(
                "Já existe uma tarefa clonada para este membro a partir desta tarefa de origem."
            )

        # 7. Clonagem independente da tarefa no setor determinado
        nova_task = Task(
            usuario_id=assignment.atribuido_id,
            setor_id=setor_destino_id,
            origem_task_id=task_orig.id,
            titulo=task_orig.titulo,
            descricao=task_orig.descricao,
            status="PENDENTE",
            prazo_conclusao=task_orig.prazo_conclusao,
        )
        create_task(db, nova_task, commit=False)

        # Só vincula à weekly se a janela estiver aberta e o relatório estiver em RASCUNHO
        # Bloqueia a weekly com lock pessimista para evitar vincular a relatórios aprovados concorrentemente
        if dentro_da_janela():
            semana_atual = obter_semana_referencia()
            weekly_convidado = (
                db.query(Weekly)
                .filter(
                    Weekly.usuario_id == assignment.atribuido_id,
                    Weekly.setor_id == setor_destino_id,
                    Weekly.semana_referencia == semana_atual,
                )
                .with_for_update()
                .first()
            )
            if weekly_convidado and weekly_convidado.status == "RASCUNHO":
                proxima_pos = get_next_weekly_task_posicao(db, weekly_convidado.id)
                weekly_item = WeeklyTask(
                    weekly_id=weekly_convidado.id,
                    task_id=nova_task.id,
                    concluida=False,
                    origem="NOVA",
                    posicao=proxima_pos,
                )
                add_task_to_weekly(db, weekly_item, commit=False)

        try:
            commit_changes(db)
        except IntegrityError:
            db.rollback()
            raise BadRequestError(
                "Este convite já foi aceito ou a tarefa já foi clonada anteriormente."
            )

        db.refresh(assignment)

        if assignment.solicitante and assignment.solicitante.email:
            try:
                enviar_email_resposta_convite_task(
                    destinatario=assignment.solicitante.email,
                    titulo_task=task_orig.titulo,
                    nome_solicitante=assignment.solicitante.nome_completo,
                    nome_atribuido=current_user.nome_completo,
                    setor_nome=task_orig.setor.nome
                    if task_orig.setor
                    else "Geral",
                    aceitou=True,
                )
            except (smtplib.SMTPException, OSError):
                logger.exception(
                    "❌ Falha ao enviar e-mail de resposta positiva de convite"
                )
    else:
        # Transição atômica condicional de status para RECUSADA
        rows_updated = (
            db.query(TaskAssignment)
            .filter(
                TaskAssignment.id == assignment.id,
                TaskAssignment.status == "PENDENTE",
            )
            .update(
                {
                    TaskAssignment.status: "RECUSADA",
                    TaskAssignment.respondido_em: agora_utc,
                },
                synchronize_session="fetch",
            )
        )
        if rows_updated == 0:
            raise BadRequestError(
                "Este convite já foi respondido ou não está mais pendente."
            )

        commit_changes(db)
        db.refresh(assignment)

        if assignment.solicitante and assignment.solicitante.email:
            try:
                enviar_email_resposta_convite_task(
                    destinatario=assignment.solicitante.email,
                    titulo_task=task_orig.titulo,
                    nome_solicitante=assignment.solicitante.nome_completo,
                    nome_atribuido=current_user.nome_completo,
                    setor_nome=task_orig.setor.nome
                    if task_orig.setor
                    else "Geral",
                    aceitou=False,
                )
            except (smtplib.SMTPException, OSError):
                logger.exception(
                    "❌ Falha ao enviar e-mail de recusa de convite"
                )

    return _format_assignment_response(assignment)


def svc_list_my_assignments(
    tipo: str,
    status: str | None,
    pagina: int,
    limite: int,
    current_user: User,
    db: Session,
) -> TaskAssignmentListResponse:
    """Lista os convites de atribuição enviados ou recebidos pelo usuário autenticado."""
    if tipo not in ("recebidas", "enviadas"):
        raise BadRequestError(
            "O parâmetro 'tipo' deve ser 'recebidas' ou 'enviadas'."
        )
    if status and status not in ("PENDENTE", "ACEITA", "RECUSADA", "EXPIRADA"):
        raise BadRequestError(f"Status de convite inválido: {status}.")

    assignments, total = list_assignments_by_user(
        db=db,
        user_id=current_user.id,
        tipo=tipo,
        status=status,
        pagina=pagina,
        limite=limite,
    )
    return TaskAssignmentListResponse(
        atribuicoes=[_format_assignment_response(a) for a in assignments],
        total=total,
        pagina=pagina,
        limite=limite,
    )


def svc_list_eligible_collaborators(
    solicitante_id: UUID,
    task_id: UUID | None,
    busca: str | None,
    pagina: int,
    limite: int,
    db: Session,
) -> ColaboradoresElegiveisResponse:
    """Lista colaboradores elegíveis para receber atribuição de tarefas."""
    usuarios, total = find_eligible_collaborators(
        db,
        solicitante_id=solicitante_id,
        task_id=task_id,
        busca=busca,
        pagina=pagina,
        limite=limite,
    )

    itens = []
    for u in usuarios:
        setores_nomes = [
            su.setor.nome for su in u.setores if su.setor and su.setor.ativo
        ]
        itens.append(
            ColaboradorElegivelItem(
                id=u.id,
                nome_completo=u.nome_completo,
                email=u.email,
                matricula=u.matricula,
                setores=setores_nomes,
            )
        )

    return ColaboradoresElegiveisResponse(
        colaboradores=itens,
        total=total,
        pagina=pagina,
        limite=limite,
    )


# ── Dashboard (Fase 11) ──────────────────────────────────────


def _calcular_metricas_setor(
    setor_id: UUID, setor_nome: str, semana_referencia: date, db: Session
) -> SectorDashboardResponse:
    """Calcula e formata métricas consolidadas de um setor em uma semana."""
    total_membros_vinculados = count_active_members_by_sector(
        db, setor_id, ate_data=semana_referencia
    )
    weeklies = find_weeklies_by_sector_and_semana(db, setor_id, semana_referencia)

    enviadas = sum(1 for w in weeklies if w.status == "ENVIADA")
    aprovadas = sum(1 for w in weeklies if w.status == "APROVADA")
    rejeitadas = sum(1 for w in weeklies if w.status == "REJEITADA")
    expiradas = sum(1 for w in weeklies if w.status == "EXPIRADA")
    rascunhos = sum(1 for w in weeklies if w.status == "RASCUNHO")

    submetidas = enviadas + aprovadas + rejeitadas + expiradas
    # O denominador histórico considera a quantidade de membros vinculados até aquela data,
    # sendo no mínimo a quantidade de membros que possuem relatório registrado na semana.
    membros_com_relatorio = len({w.usuario_id for w in weeklies})
    total_membros = max(total_membros_vinculados, membros_com_relatorio)

    taxa = (
        min(round((submetidas / total_membros) * 100.0, 1), 100.0)
        if total_membros > 0
        else 0.0
    )

    all_weekly_tasks = [weekly_task for w in weeklies for weekly_task in w.weekly_tasks]
    total_tasks_semana = len(all_weekly_tasks)
    tasks_concluidas = sum(1 for weekly_task in all_weekly_tasks if weekly_task.concluida)
    total_impedimentos = sum(1 for weekly_task in all_weekly_tasks if weekly_task.impedimento)

    tasks_pendentes = count_pending_tasks_by_sector(db, setor_id)
    tasks_em_auditoria = count_tasks_in_audit_by_sector(db, setor_id)

    return SectorDashboardResponse(
        setor_id=setor_id,
        setor_nome=setor_nome,
        semana_referencia=semana_referencia,
        total_membros=total_membros,
        weeklies_enviadas=enviadas,
        weeklies_aprovadas=aprovadas,
        weeklies_rejeitadas=rejeitadas,
        weeklies_expiradas=expiradas,
        weeklies_rascunho=rascunhos,
        taxa_submissao_percentual=taxa,
        total_tasks=total_tasks_semana,
        tasks_concluidas=tasks_concluidas,
        tasks_pendentes=tasks_pendentes,
        tasks_em_auditoria=tasks_em_auditoria,
        total_impedimentos=total_impedimentos,
    )


def svc_get_sector_dashboard(
    setor_id: UUID,
    semana_referencia: date | None,
    current_user: User,
    db: Session,
) -> SectorDashboardResponse:
    """Retorna métricas analíticas de um setor específico para a semana indicada.

    Permitido para líderes do setor ou administradores.
    """
    if not (_is_admin(current_user) or _is_lider_do_setor(db, setor_id, current_user)):
        raise ForbiddenError(
            "Apenas líderes deste setor ou administradores podem acessar este dashboard."
        )

    sector = find_sector_by_id(db, setor_id)
    if not sector:
        raise NotFoundError("Setor não encontrado.")

    if semana_referencia is None:
        semana_referencia = obter_semana_referencia()

    return _calcular_metricas_setor(
        setor_id=sector.id,
        setor_nome=sector.nome,
        semana_referencia=semana_referencia,
        db=db,
    )


def svc_get_global_dashboard(
    semana_referencia: date | None,
    current_user: User,
    db: Session,
) -> GlobalDashboardResponse:
    """Retorna métricas consolidadas de todos os setores ativos (apenas admin/super_admin)."""
    if current_user.global_role not in (RoleID.ADMIN, RoleID.SUPER_ADMIN):
        raise ForbiddenError(
            "Apenas administradores podem acessar o dashboard geral."
        )

    if semana_referencia is None:
        semana_referencia = obter_semana_referencia()

    active_sectors = find_all_active_sectors(db)
    setores_metrics = [
        _calcular_metricas_setor(
            setor_id=s.id,
            setor_nome=s.nome,
            semana_referencia=semana_referencia,
            db=db,
        )
        for s in active_sectors
    ]

    total_membros = sum(s.total_membros for s in setores_metrics)
    total_enviadas = sum(s.weeklies_enviadas for s in setores_metrics)
    total_aprovadas = sum(s.weeklies_aprovadas for s in setores_metrics)
    total_rejeitadas = sum(s.weeklies_rejeitadas for s in setores_metrics)
    total_expiradas = sum(s.weeklies_expiradas for s in setores_metrics)
    total_rascunhos = sum(s.weeklies_rascunho for s in setores_metrics)

    total_submetidas = total_enviadas + total_aprovadas + total_rejeitadas + total_expiradas
    taxa_geral = (
        min(round((total_submetidas / total_membros) * 100.0, 1), 100.0)
        if total_membros > 0
        else 0.0
    )

    total_tasks_auditoria = sum(s.tasks_em_auditoria for s in setores_metrics)
    total_impedimentos = sum(s.total_impedimentos for s in setores_metrics)

    return GlobalDashboardResponse(
        semana_referencia=semana_referencia,
        total_setores=len(active_sectors),
        total_membros=total_membros,
        total_weeklies_enviadas=total_enviadas,
        total_weeklies_aprovadas=total_aprovadas,
        total_weeklies_rejeitadas=total_rejeitadas,
        total_weeklies_expiradas=total_expiradas,
        total_weeklies_rascunho=total_rascunhos,
        taxa_submissao_geral_percentual=taxa_geral,
        total_tasks_em_auditoria=total_tasks_auditoria,
        total_impedimentos=total_impedimentos,
        setores=setores_metrics,
    )




