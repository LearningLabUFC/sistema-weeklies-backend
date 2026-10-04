"""Repository — Acesso a dados de Sessões de Trabalho."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.pause import Pause
from app.models.sector import Sector
from app.models.user import User
from app.models.work_session import WorkSession, WorkSessionStatus

# ── Sessões de Trabalho ──────────────────────────────────────


def create_work_session(
    db: Session,
    work_session: WorkSession,
) -> WorkSession:
    """Persiste uma nova sessão de trabalho no banco."""
    db.add(work_session)
    db.commit()
    db.refresh(work_session)
    return work_session


def find_work_session_by_id(
    db: Session,
    session_id: UUID,
) -> WorkSession | None:
    """Busca uma sessão de trabalho pelo ID."""
    return (
        db.query(WorkSession)
        .filter(WorkSession.id == session_id)
        .first()
    )


def find_open_session_by_user_id(
    db: Session,
    user_id: UUID,
) -> WorkSession | None:
    """Busca a sessão atualmente aberta de um usuário."""
    return (
        db.query(WorkSession)
        .filter(
            WorkSession.usuario_id == user_id,
            WorkSession.saida.is_(None),
        )
        .first()
    )


def update_work_session(
    db: Session,
    work_session: WorkSession,
) -> WorkSession:
    """Persiste as alterações feitas na sessão."""
    db.commit()
    db.refresh(work_session)
    return work_session

# ── Pausas ───────────────────────────────────────────────────


def create_pause(
    db: Session,
    pause: Pause,
) -> Pause:
    """Persiste uma nova pausa no banco."""
    db.add(pause)
    db.commit()
    db.refresh(pause)
    return pause


def find_pause_by_id(
    db: Session,
    pause_id: UUID,
) -> Pause | None:
    """Busca uma pausa pelo ID."""
    return db.query(Pause).filter(Pause.id == pause_id).first()


def find_open_pause_by_session_id(
    db: Session,
    session_id: UUID,
) -> Pause | None:
    """Busca a pausa atualmente aberta de uma sessão."""
    return (
        db.query(Pause)
        .filter(
            Pause.sessao_trabalho_id == session_id,
            Pause.fim.is_(None),
        )
        .first()
    )


def list_pauses_by_session_id(
    db: Session,
    session_id: UUID,
) -> list[Pause]:
    """Lista todas as pausas de uma sessão ordenadas por início."""
    return (
        db.query(Pause)
        .filter(Pause.sessao_trabalho_id == session_id)
        .order_by(Pause.inicio.asc())
        .all()
    )


def update_pause(
    db: Session,
    pause: Pause,
) -> Pause:
    """Persiste as alterações feitas na pausa."""
    db.commit()
    db.refresh(pause)
    return pause

def commit_started_pause(
    db: Session,
    work_session: WorkSession,
    pause: Pause,
) -> None:
    db.add(work_session)
    db.add(pause)

    db.commit()

    db.refresh(work_session)
    db.refresh(pause)


def commit_finished_pause(
    db: Session,
    work_session: WorkSession,
    pause: Pause,
) -> None:
    db.add(work_session)
    db.add(pause)

    db.commit()

    db.refresh(work_session)
    db.refresh(pause)

# ── Listagem e Paginação ─────────────────────────────────────


def list_work_sessions_paginated(
    db: Session,
    pagina: int,
    limite: int,
    usuario_id: UUID | None = None,
    setor_id: UUID | None = None,
    status: WorkSessionStatus | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
) -> tuple[list[WorkSession], int]:
    """Retorna sessões com filtros e paginação."""
    query = db.query(WorkSession)

    if usuario_id:
        query = query.filter(
            WorkSession.usuario_id == usuario_id
        )

    if setor_id:
        query = query.filter(
            WorkSession.setor_id == setor_id
        )

    if status:
        query = query.filter(
            WorkSession.status == status
        )

    if inicio is not None and fim is not None:
        query = query.filter(
            WorkSession.entrada < fim,
            (
                WorkSession.saida.is_(None)
                | (WorkSession.saida > inicio)
            ),
        )

    total = query.count()
    offset = (pagina - 1) * limite

    sessoes = (
        query.order_by(WorkSession.entrada.desc())
        .offset(offset)
        .limit(limite)
        .all()
    )

    return sessoes, total


# ── Consultas para Métricas e Resumos ────────────────────────


def find_sessions_in_period(
    db: Session,
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = None,
    setor_id: UUID | None = None,
) -> list[WorkSession]:
    """Busca sessões que possuem sobreposição com o período informado."""
    query = db.query(WorkSession).filter(
        WorkSession.entrada < fim,
        (
            WorkSession.saida.is_(None)
            | (WorkSession.saida > inicio)
        ),
    )

    if usuario_id:
        query = query.filter(
            WorkSession.usuario_id == usuario_id
        )

    if setor_id:
        query = query.filter(
            WorkSession.setor_id == setor_id
        )

    return query.order_by(WorkSession.entrada.asc()).all()


def find_expired_open_sessions(
    db: Session,
    now: datetime,
) -> list[WorkSession]:
    """Busca sessões abertas que já atingiram a expiração."""
    return (
        db.query(WorkSession)
        .filter(
            WorkSession.saida.is_(None),
            WorkSession.expiracao.is_not(None),
            WorkSession.expiracao <= now,
            WorkSession.status.in_(
                [
                    WorkSessionStatus.ATIVA,
                    WorkSessionStatus.EM_PAUSA,
                ]
            ),
        )
        .all()
    )


def count_sessions_started_in_period(
    db: Session,
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = None,
    setor_id: UUID | None = None,
) -> int:
    """Conta sessões iniciadas no período [inicio, fim)."""
    query = db.query(
        func.count(WorkSession.id)
    ).filter(
        WorkSession.entrada >= inicio,
        WorkSession.entrada < fim,
    )

    if usuario_id:
        query = query.filter(
            WorkSession.usuario_id == usuario_id
        )

    if setor_id:
        query = query.filter(
            WorkSession.setor_id == setor_id
        )

    return query.scalar() or 0


def list_users_with_sessions_in_period(
    db: Session,
    inicio: datetime,
    fim: datetime,
    setor_id: UUID | None = None,
) -> list[User]:
    """Lista usuários distintos que possuem sessões no período."""
    query = (
        db.query(User)
        .join(
            WorkSession,
            WorkSession.usuario_id == User.id,
        )
        .filter(
            WorkSession.entrada < fim,
            (
                WorkSession.saida.is_(None)
                | (WorkSession.saida > inicio)
            ),
        )
    )

    if setor_id:
        query = query.filter(
            WorkSession.setor_id == setor_id
        )

    return (
        query.distinct()
        .order_by(User.nome_completo.asc())
        .all()
    )

def list_sectors_with_sessions_in_period(
    db: Session,
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None = None,
) -> list[Sector]:
    """Lista setores distintos que possuem sessões no período."""
    query = (
        db.query(Sector)
        .join(
            WorkSession,
            WorkSession.setor_id == Sector.id,
        )
        .filter(
            WorkSession.entrada < fim,
            (
                WorkSession.saida.is_(None)
                | (WorkSession.saida > inicio)
            ),
        )
    )

    if usuario_id:
        query = query.filter(
            WorkSession.usuario_id == usuario_id
        )

    return (
        query.distinct()
        .order_by(Sector.id.asc())
        .all()
    )

def commit_expired_work_session(
    db: Session,
    work_session: WorkSession,
    pause: Pause | None = None,
) -> None:
    if pause is not None:
        db.add(pause)

    db.add(work_session)
    db.commit()

    db.refresh(work_session)

    if pause is not None:
        db.refresh(pause)

def commit_finished_work_session(
    db: Session,
    work_session: WorkSession,
    pause: Pause | None = None,
) -> None:
    if pause is not None:
        db.add(pause)

    db.add(work_session)
    db.commit()

    db.refresh(work_session)

    if pause is not None:
        db.refresh(pause)