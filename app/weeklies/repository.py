"""Repository — Acesso a dados de Tasks, Weeklies e WeeklyTasks."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import RoleID, StatusID
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.models.weekly_warning import WeeklyWarning

# ── Task ─────────────────────────────────────────────────────


def create_task(db: Session, task: Task, commit: bool = True) -> Task:
    """Persiste uma nova task no banco. Se commit=False, apenas executa flush."""
    db.add(task)
    if commit:
        db.commit()
        db.refresh(task)
    else:
        db.flush()
    return task


def find_task_by_id(
    db: Session, task_id: UUID, for_update: bool = False
) -> Task | None:
    """Busca uma task pelo ID, opcionalmente adquirindo lock exclusivo (SELECT FOR UPDATE)."""
    query = db.query(Task).filter(Task.id == task_id)
    if for_update:
        query = query.with_for_update()
    return query.first()


def list_weeklies_by_task(db: Session, task_id: UUID) -> list[Weekly]:
    """Relatórios que compartilham o texto da tarefa, inclusive os históricos."""
    return (
        db.query(Weekly)
        .join(WeeklyTask, WeeklyTask.weekly_id == Weekly.id)
        .filter(WeeklyTask.task_id == task_id)
        .all()
    )


def list_tasks_by_user_sector(
    db: Session,
    usuario_id: UUID,
    setor_id: UUID,
    status_filter: str | None,
    pagina: int,
    limite: int,
) -> tuple[list[Task], int]:
    """Retorna (lista_de_tasks, total) de um membro em um setor com paginação."""
    query = db.query(Task).filter(
        Task.usuario_id == usuario_id,
        Task.setor_id == setor_id,
    )
    if status_filter:
        query = query.filter(Task.status == status_filter)

    total = query.count()
    offset = (pagina - 1) * limite
    tasks = query.order_by(Task.criado_em.desc()).offset(offset).limit(limite).all()
    return tasks, total


def list_tasks_by_user(
    db: Session,
    usuario_id: UUID,
    status_filter: str | None,
    pagina: int,
    limite: int,
) -> tuple[list[Task], int]:
    """Retorna (lista_de_tasks, total) de um membro (todos os setores) com paginação."""
    query = db.query(Task).filter(Task.usuario_id == usuario_id)
    if status_filter:
        query = query.filter(Task.status == status_filter)

    total = query.count()
    offset = (pagina - 1) * limite
    tasks = query.order_by(Task.criado_em.desc()).offset(offset).limit(limite).all()
    return tasks, total


def update_task(db: Session) -> None:
    """Persiste as alterações feitas nos objetos Task."""
    db.commit()


def delete_task_soft(db: Session, task: Task, removida_por_id: UUID) -> None:
    """Soft delete: marca task como REMOVIDA_PELO_LIDER."""
    task.status = "REMOVIDA_PELO_LIDER"
    task.removida_por = removida_por_id
    db.commit()


# ── Weekly ───────────────────────────────────────────────────


def find_weekly_by_id(
    db: Session, weekly_id: UUID, for_update: bool = False
) -> Weekly | None:
    """Busca uma weekly pelo ID carregando seus vínculos.

    Se for_update=True, adquire lock exclusivo na linha da weekly (SELECT FOR UPDATE)
    garantindo que alterações ou avaliações concorrentes sejam serializadas e vejam
    o estado mais recente no banco de dados.
    """
    if for_update:
        locked = (
            db.query(Weekly)
            .filter(Weekly.id == weekly_id)
            .with_for_update()
            .first()
        )
        if not locked:
            return None
        return (
            db.query(Weekly)
            .options(
                joinedload(Weekly.usuario),
                joinedload(Weekly.weekly_tasks).joinedload(WeeklyTask.task),
            )
            .populate_existing()
            .filter(Weekly.id == weekly_id)
            .first()
        )

    return (
        db.query(Weekly)
        .options(
            joinedload(Weekly.usuario),
            joinedload(Weekly.weekly_tasks).joinedload(WeeklyTask.task),
        )
        .filter(Weekly.id == weekly_id)
        .first()
    )


def find_weekly_by_user_sector_semana(
    db: Session, usuario_id: UUID, setor_id: UUID, semana_referencia: date
) -> Weekly | None:
    """Busca weekly por usuário, setor e semana de referência."""
    return (
        db.query(Weekly)
        .options(
            joinedload(Weekly.weekly_tasks).joinedload(WeeklyTask.task)
        )
        .filter(
            Weekly.usuario_id == usuario_id,
            Weekly.setor_id == setor_id,
            Weekly.semana_referencia == semana_referencia,
        )
        .first()
    )


def create_weekly(db: Session, weekly: Weekly, commit: bool = True) -> Weekly:
    """Persiste uma nova weekly no banco. Se commit=False, apenas executa flush."""
    db.add(weekly)
    if commit:
        db.commit()
        db.refresh(weekly)
    else:
        db.flush()
    return weekly


def find_pending_tasks_for_rollover(
    db: Session, usuario_id: UUID, setor_id: UUID
) -> list[Task]:
    """
    Retorna todas as tasks PENDENTES de um membro em um setor para herança/rollover (Fase 4).
    Ordenadas cronologicamente por criado_em crescente.
    Tarefas CONCLUIDA, EM_AUDITORIA ou REMOVIDA_PELO_LIDER não são incluídas.
    """
    return (
        db.query(Task)
        .filter(
            Task.usuario_id == usuario_id,
            Task.setor_id == setor_id,
            Task.status == "PENDENTE",
        )
        .order_by(Task.criado_em.asc())
        .all()
    )


def list_weeklies_by_user(
    db: Session,
    usuario_id: UUID,
    setor_id: UUID | None,
    status_filter: str | None,
    pagina: int,
    limite: int,
) -> tuple[list[Weekly], int]:
    """Retorna (lista_de_weeklies, total) do usuário com paginação e filtros."""
    query = (
        db.query(Weekly)
        .options(
            joinedload(Weekly.usuario),
            joinedload(Weekly.weekly_tasks)
        )
        .filter(Weekly.usuario_id == usuario_id)
    )
    if setor_id:
        query = query.filter(Weekly.setor_id == setor_id)
    if status_filter:
        query = query.filter(Weekly.status == status_filter)

    total = query.count()
    offset = (pagina - 1) * limite
    weeklies = (
        query.order_by(Weekly.semana_referencia.desc(), Weekly.criado_em.desc())
        .offset(offset)
        .limit(limite)
        .all()
    )
    return weeklies, total


def list_weeklies_by_sector(
    db: Session,
    setor_id: UUID,
    status_filter: str | None,
    pagina: int,
    limite: int,
) -> tuple[list[Weekly], int]:
    """Retorna weeklies de um setor (usado por líderes) com paginação e filtros."""
    query = (
        db.query(Weekly)
        .options(
            joinedload(Weekly.usuario),
            joinedload(Weekly.weekly_tasks)
        )
        .filter(Weekly.setor_id == setor_id)
    )
    if status_filter:
        query = query.filter(Weekly.status == status_filter)

    total = query.count()
    offset = (pagina - 1) * limite
    weeklies = (
        query.order_by(Weekly.semana_referencia.desc(), Weekly.criado_em.desc())
        .offset(offset)
        .limit(limite)
        .all()
    )
    return weeklies, total


# ── WeeklyTask ───────────────────────────────────────────────


def find_weekly_task(db: Session, weekly_id: UUID, task_id: UUID) -> WeeklyTask | None:
    """Verifica se uma task já está vinculada a uma weekly."""
    return (
        db.query(WeeklyTask)
        .filter(
            WeeklyTask.weekly_id == weekly_id,
            WeeklyTask.task_id == task_id,
        )
        .first()
    )


def find_weekly_task_by_id(
    db: Session, weekly_task_id: UUID, for_update: bool = False
) -> WeeklyTask | None:
    """Busca o item associativo de WeeklyTask pelo ID com a task associada."""
    if for_update:
        locked = (
            db.query(WeeklyTask)
            .filter(WeeklyTask.id == weekly_task_id)
            .with_for_update()
            .first()
        )
        if not locked:
            return None
        return (
            db.query(WeeklyTask)
            .options(joinedload(WeeklyTask.task))
            .populate_existing()
            .filter(WeeklyTask.id == weekly_task_id)
            .first()
        )

    return (
        db.query(WeeklyTask)
        .options(joinedload(WeeklyTask.task))
        .filter(WeeklyTask.id == weekly_task_id)
        .first()
    )


def get_next_weekly_task_posicao(db: Session, weekly_id: UUID) -> int:
    """Calcula a próxima posição sequencial de ordenação para tarefas da weekly."""
    max_pos = (
        db.query(func.max(WeeklyTask.posicao))
        .filter(WeeklyTask.weekly_id == weekly_id)
        .scalar()
    )
    return (max_pos or 0) + 1


def add_task_to_weekly(
    db: Session, weekly_task: WeeklyTask, commit: bool = True
) -> WeeklyTask:
    """Adiciona uma task à weekly. Se commit=False, apenas executa flush."""
    db.add(weekly_task)
    if commit:
        db.commit()
        db.refresh(weekly_task)
    else:
        db.flush()
    return weekly_task


def remove_task_from_weekly(db: Session, weekly_task: WeeklyTask) -> None:
    """Remove o vínculo da task com a weekly."""
    db.delete(weekly_task)
    db.commit()


def commit_changes(db: Session) -> None:
    """Comita alterações pendentes no banco."""
    db.commit()


# ── Vínculo Setor-Usuário (leitura) ─────────────────────────


def find_sector_user(db: Session, setor_id: UUID, usuario_id: UUID) -> SectorUser | None:
    """Busca a associação de um usuário em um setor."""
    return (
        db.query(SectorUser)
        .filter(
            SectorUser.setor_id == setor_id,
            SectorUser.usuario_id == usuario_id,
        )
        .first()
    )


def find_active_sector_members(db: Session) -> list[SectorUser]:
    """Retorna todos os vínculos de membros com status ATIVO em setores ativos,
    excluindo administradores e super administradores da obrigação semanal.
    """
    from app.core.constants import RoleID, StatusID
    from app.models.sector import Sector
    from app.models.user import User

    return (
        db.query(SectorUser)
        .join(User, SectorUser.usuario_id == User.id)
        .join(Sector, SectorUser.setor_id == Sector.id)
        .filter(
            User.status_id == StatusID.ATIVO,
            Sector.ativo.is_(True),
            SectorUser.papel.in_(["membro", "lider"]),
            User.global_role.notin_([RoleID.ADMIN, RoleID.SUPER_ADMIN]),
        )
        .all()
    )


# ── Advertências (Fase 7) ────────────────────────────────────


def create_warning(
    db: Session, warning: WeeklyWarning, commit: bool = True
) -> WeeklyWarning:
    """Persiste uma nova advertência no banco de dados."""
    db.add(warning)
    if commit:
        db.commit()
        db.refresh(warning)
    else:
        db.flush()
    return warning


def find_warning_by_user_sector_semana(
    db: Session, usuario_id: UUID, setor_id: UUID, semana_referencia: date
) -> WeeklyWarning | None:
    """Busca advertência já emitida para o usuário, setor e semana."""
    return (
        db.query(WeeklyWarning)
        .options(
            joinedload(WeeklyWarning.usuario),
            joinedload(WeeklyWarning.setor),
        )
        .filter(
            WeeklyWarning.usuario_id == usuario_id,
            WeeklyWarning.setor_id == setor_id,
            WeeklyWarning.semana_referencia == semana_referencia,
        )
        .first()
    )


def list_warnings_by_sector(
    db: Session,
    setor_id: UUID,
    pagina: int = 1,
    limite: int = 20,
) -> tuple[list[WeeklyWarning], int]:
    """Retorna (lista_de_advertencias, total) de um setor com paginação."""
    query = (
        db.query(WeeklyWarning)
        .options(
            joinedload(WeeklyWarning.usuario),
            joinedload(WeeklyWarning.setor),
        )
        .filter(WeeklyWarning.setor_id == setor_id)
    )
    total = query.count()
    offset = (pagina - 1) * limite
    warnings = (
        query.order_by(WeeklyWarning.criado_em.desc())
        .offset(offset)
        .limit(limite)
        .all()
    )
    return warnings, total


def list_warnings_by_user(
    db: Session,
    usuario_id: UUID,
    setor_id: UUID | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> tuple[list[WeeklyWarning], int]:
    """Retorna (lista_de_advertencias, total) de um usuário com paginação."""
    query = (
        db.query(WeeklyWarning)
        .options(
            joinedload(WeeklyWarning.usuario),
            joinedload(WeeklyWarning.setor),
        )
        .filter(WeeklyWarning.usuario_id == usuario_id)
    )
    if setor_id:
        query = query.filter(WeeklyWarning.setor_id == setor_id)

    total = query.count()
    offset = (pagina - 1) * limite
    warnings = (
        query.order_by(WeeklyWarning.criado_em.desc())
        .offset(offset)
        .limit(limite)
        .all()
    )
    return warnings, total


# ── Auditoria de Tasks (Fase 8) ──────────────────────────────


def find_expired_pending_tasks(db: Session, data_limite: date) -> list[Task]:
    """Retorna todas as tasks com status PENDENTE cujo prazo_conclusao é anterior a data_limite."""
    return (
        db.query(Task)
        .options(joinedload(Task.usuario), joinedload(Task.setor))
        .filter(
            Task.status == "PENDENTE",
            Task.prazo_conclusao.isnot(None),
            Task.prazo_conclusao < data_limite,
        )
        .all()
    )


def find_tasks_in_audit(
    db: Session,
    setor_id: UUID | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> tuple[list[Task], int]:
    """Retorna (tasks, total) com status EM_AUDITORIA, opcionalmente filtradas por setor."""
    query = (
        db.query(Task)
        .options(joinedload(Task.usuario), joinedload(Task.setor))
        .filter(Task.status == "EM_AUDITORIA")
    )
    if setor_id:
        query = query.filter(Task.setor_id == setor_id)

    total = query.count()
    offset = (pagina - 1) * limite
    tasks = (
        query.order_by(Task.entrada_auditoria_em.asc())
        .offset(offset)
        .limit(limite)
        .all()
    )
    return tasks, total


def find_sector_leaders(db: Session, setor_id: UUID) -> list[User]:
    """Retorna os líderes ativos de um setor."""
    return (
        db.query(User)
        .join(SectorUser, SectorUser.usuario_id == User.id)
        .filter(
            SectorUser.setor_id == setor_id,
            SectorUser.papel == "lider",
            User.status_id == StatusID.ATIVO,
        )
        .all()
    )


def find_admin_users(db: Session) -> list[User]:
    """Retorna todos os usuários com papel global admin ou super_admin ativos."""
    return (
        db.query(User)
        .filter(
            User.global_role.in_([RoleID.ADMIN, RoleID.SUPER_ADMIN]),
            User.status_id == StatusID.ATIVO,
        )
        .all()
    )


# ── TaskAssignment (Fase 9) ──────────────────────────────────


def create_task_assignment(
    db: Session, assignment: TaskAssignment, commit: bool = True
) -> TaskAssignment:
    """Persiste um novo convite de atribuição de task."""
    db.add(assignment)
    if commit:
        db.commit()
        db.refresh(assignment)
    else:
        db.flush()
    return assignment


def find_assignment_by_id(
    db: Session, assignment_id: UUID, for_update: bool = False
) -> TaskAssignment | None:
    """Busca um convite de atribuição pelo ID com relacionamentos carregados.

    Se for_update=True, adquire lock exclusivo (SELECT FOR UPDATE) na linha do convite,
    garantindo que respostas concorrentes sejam serializadas e vejam o status atualizado.
    """
    if for_update:
        locked = (
            db.query(TaskAssignment)
            .filter(TaskAssignment.id == assignment_id)
            .with_for_update()
            .first()
        )
        if not locked:
            return None
        return (
            db.query(TaskAssignment)
            .options(
                joinedload(TaskAssignment.task),
                joinedload(TaskAssignment.solicitante),
                joinedload(TaskAssignment.atribuido),
            )
            .populate_existing()
            .filter(TaskAssignment.id == assignment_id)
            .first()
        )

    return (
        db.query(TaskAssignment)
        .options(
            joinedload(TaskAssignment.task),
            joinedload(TaskAssignment.solicitante),
            joinedload(TaskAssignment.atribuido),
        )
        .filter(TaskAssignment.id == assignment_id)
        .first()
    )


def find_pending_assignment_by_task_and_user(
    db: Session, task_id: UUID, atribuido_id: UUID
) -> TaskAssignment | None:
    """Verifica se já existe um convite PENDENTE para a mesma task e membro atribuído."""
    return (
        db.query(TaskAssignment)
        .filter(
            TaskAssignment.task_id == task_id,
            TaskAssignment.atribuido_id == atribuido_id,
            TaskAssignment.status == "PENDENTE",
        )
        .first()
    )


def list_assignments_by_user(
    db: Session,
    user_id: UUID,
    tipo: str = "recebidas",
    status: str | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> tuple[list[TaskAssignment], int]:
    """Lista convites de atribuição de tarefas (recebidas ou enviadas) com paginação."""
    query = db.query(TaskAssignment).options(
        joinedload(TaskAssignment.task),
        joinedload(TaskAssignment.solicitante),
        joinedload(TaskAssignment.atribuido),
    )

    if tipo == "enviadas":
        query = query.filter(TaskAssignment.solicitante_id == user_id)
    else:  # recebidas (default)
        query = query.filter(TaskAssignment.atribuido_id == user_id)

    if status:
        query = query.filter(TaskAssignment.status == status)

    total = query.count()
    assignments = (
        query.order_by(TaskAssignment.criado_em.desc())
        .offset((pagina - 1) * limite)
        .limit(limite)
        .all()
    )
    return assignments, total


# ── Dashboard (Fase 11) ──────────────────────────────────────


def find_sector_by_id(db: Session, setor_id: UUID) -> Sector | None:
    """Busca um setor pelo ID."""
    return db.query(Sector).filter(Sector.id == setor_id).first()


def find_all_active_sectors(db: Session) -> list[Sector]:
    """Retorna todos os setores ativos ordenados por nome."""
    return (
        db.query(Sector)
        .filter(Sector.ativo.is_(True))
        .order_by(Sector.nome.asc())
        .all()
    )


def count_active_members_by_sector(
    db: Session, setor_id: UUID, ate_data: date | None = None
) -> int:
    """Conta membros com vínculo ativo no setor informado.
    Se 'ate_data' for informada, considera apenas vínculos iniciados até aquela data.
    """
    query = (
        db.query(SectorUser)
        .join(User, User.id == SectorUser.usuario_id)
        .filter(
            SectorUser.setor_id == setor_id,
            User.status_id == StatusID.ATIVO,
        )
    )
    if ate_data:
        from sqlalchemy import func

        data_inicio = func.coalesce(
            SectorUser.data_ingresso,
            User.data_ingresso,
            func.date(SectorUser.criado_em),
        )
        query = query.filter(data_inicio <= ate_data)

    return query.count()


def find_weeklies_by_sector_and_semana(
    db: Session, setor_id: UUID, semana_referencia: date
) -> list[Weekly]:
    """Retorna todas as weeklies de um setor para uma semana de referência com tasks carregadas."""
    return (
        db.query(Weekly)
        .options(joinedload(Weekly.weekly_tasks).joinedload(WeeklyTask.task))
        .filter(
            Weekly.setor_id == setor_id,
            Weekly.semana_referencia == semana_referencia,
        )
        .all()
    )


def count_tasks_in_audit_by_sector(db: Session, setor_id: UUID) -> int:
    """Conta total de tarefas em status EM_AUDITORIA no setor."""
    return (
        db.query(Task)
        .filter(
            Task.setor_id == setor_id,
            Task.status == "EM_AUDITORIA",
        )
        .count()
    )


def count_pending_tasks_by_sector(db: Session, setor_id: UUID) -> int:
    """Conta total de tarefas em status PENDENTE no setor."""
    return (
        db.query(Task)
        .filter(
            Task.setor_id == setor_id,
            Task.status == "PENDENTE",
        )
        .count()
    )


def find_eligible_collaborators(
    db: Session,
    solicitante_id: UUID,
    task_id: UUID | None = None,
    busca: str | None = None,
    pagina: int = 1,
    limite: int = 20,
) -> tuple[list[User], int]:
    """Retorna colaboradores ativos e elegíveis para receber tarefas.

    Critérios de elegibilidade:
    - Status ativo
    - Não é super_admin nem admin (cargos de gestão/coordenação não recebem tarefas)
    - Não é o próprio usuário solicitante
    - Possui vínculo ativo com ao menos um setor
    - Se informado task_id:
      - Não é o proprietário da tarefa
      - Não possui atribuição PENDENTE para a tarefa
      - Não possui cópia clonada da tarefa
    - Suporta busca case-insensitive por nome, email ou matrícula.
    """
    subquery_com_setor = db.query(SectorUser.usuario_id).distinct()

    query = (
        db.query(User)
        .filter(
            User.status_id == StatusID.ATIVO,
            User.global_role.notin_([RoleID.SUPER_ADMIN, RoleID.ADMIN]),
            User.id != solicitante_id,
            User.id.in_(subquery_com_setor),
        )
    )

    if task_id:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            query = query.filter(User.id != task.usuario_id)

        subquery_pendentes = (
            db.query(TaskAssignment.atribuido_id)
            .filter(
                TaskAssignment.task_id == task_id,
                TaskAssignment.status == "PENDENTE",
            )
        )
        query = query.filter(User.id.notin_(subquery_pendentes))

        subquery_clones = (
            db.query(Task.usuario_id)
            .filter(Task.origem_task_id == task_id)
        )
        query = query.filter(User.id.notin_(subquery_clones))

    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        query = query.filter(
            or_(
                User.nome_completo.ilike(termo),
                User.email.ilike(termo),
                User.matricula.ilike(termo),
            )
        )

    total = query.count()
    offset = (pagina - 1) * limite
    usuarios = (
        query.options(joinedload(User.setores).joinedload(SectorUser.setor))
        .order_by(User.nome_completo.asc())
        .offset(offset)
        .limit(limite)
        .all()
    )

    return usuarios, total
