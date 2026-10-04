"""
Service — Lógica de negócios de Controle de Horas.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.core.constants import RoleName
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.models.pause import Pause
from app.models.user import User
from app.models.work_session import MotivoEncerramento, WorkSession, WorkSessionStatus
from app.sectors.repository import find_sector_by_id, find_sector_user
from app.work_sessions.repository import (
    commit_expired_work_session,
    commit_finished_pause,
    commit_finished_work_session,
    commit_started_pause,
    count_sessions_started_in_period,
    create_work_session,
    find_expired_open_sessions,
    find_open_pause_by_session_id,
    find_open_session_by_user_id,
    find_pause_by_id,
    find_sessions_in_period,
    find_work_session_by_id,
    list_pauses_by_session_id,
    list_sectors_with_sessions_in_period,
    list_users_with_sessions_in_period,
    list_work_sessions_paginated,
    update_work_session,
)
from app.work_sessions.schemas import (
    CurrentWorkSessionResponse,
    MetricsSectorItem,
    MetricsSectorsResponse,
    MetricsSummaryResponse,
    MetricsUserItem,
    MetricsUsersResponse,
    PauseItem,
    StartWorkSessionRequest,
    WorkSessionDetail,
    WorkSessionItem,
    WorkSessionListResponse,
    WorkSessionSummaryResponse,
)


def _validate_metrics_access(
    current_user: User,
) -> None:
    if current_user.role.nome not in (
        RoleName.ADMIN,
        RoleName.SUPER_ADMIN,
    ):
        raise ForbiddenError(
            "Apenas admin e super_admin podem consultar "
            "as métricas administrativas."
        )

def _calculate_pause_time_in_period(
    work_session: WorkSession,
    inicio: datetime,
    fim: datetime,
    db: Session,
) -> int:
    agora = datetime.now(timezone.utc)

    if work_session.saida is not None:
        fim_sessao = work_session.saida
    else:
        fim_sessao = min(
            agora,
            work_session.expiracao,
        )

    inicio_calculo = max(
        work_session.entrada,
        inicio,
    )

    fim_calculo = min(
        fim_sessao,
        fim,
    )

    if inicio_calculo >= fim_calculo:
        return 0

    total_pausa_segundos = 0

    pausas = list_pauses_by_session_id(
        db,
        work_session.id,
    )

    for pausa in pausas:
        inicio_pausa = max(
            pausa.inicio,
            inicio_calculo,
        )

        fim_original_pausa = (
            pausa.fim
            if pausa.fim is not None
            else fim_calculo
        )

        fim_pausa = min(
            fim_original_pausa,
            fim_calculo,
        )

        if inicio_pausa < fim_pausa:
            total_pausa_segundos += (
                fim_pausa - inicio_pausa
            ).total_seconds()

    return max(
        0,
        int(total_pausa_segundos),
    )

def _calculate_work_time(
    work_session: WorkSession,
    db: Session,
) -> int:
    agora = datetime.now(timezone.utc)

    fim_calculo = (
        work_session.saida
        if work_session.saida is not None
        else min(agora, work_session.expiracao)
    )

    tempo_total_segundos = (
        fim_calculo - work_session.entrada
    ).total_seconds()

    total_pausa_segundos = 0

    pausas = list_pauses_by_session_id(
        db,
        work_session.id,
    )

    for pausa in pausas:
        if pausa.fim is not None:
            fim_pausa = pausa.fim
        else:
            fim_pausa = fim_calculo

        total_pausa_segundos += (
            fim_pausa - pausa.inicio
        ).total_seconds()
    
    return max (0, int(tempo_total_segundos - total_pausa_segundos))  

def _calculate_work_time_in_period(
    work_session: WorkSession,
    inicio: datetime,
    fim: datetime,
    db: Session,
) -> int:
    inicio_calculo = max(
        work_session.entrada,
        inicio,
    )

    agora = datetime.now(timezone.utc)

    if work_session.saida is not None:
        fim_sessao = work_session.saida
    else:
        fim_sessao = min(
            agora,
            work_session.expiracao,
    )

    fim_calculo = min(
        fim_sessao,
        fim,
    )

    if inicio_calculo >= fim_calculo:
        return 0

    tempo_total_segundos = (
        fim_calculo - inicio_calculo
    ).total_seconds()

    total_pausa_segundos = 0

    pausas = list_pauses_by_session_id(
        db,
        work_session.id,
    )

    for pausa in pausas:
        inicio_pausa = max(
            pausa.inicio,
            inicio_calculo,
        )

        fim_original_pausa = (
            pausa.fim
            if pausa.fim is not None
            else fim_calculo
        )

        fim_pausa = min(
            fim_original_pausa,
            fim_calculo,
        )

        if inicio_pausa < fim_pausa:
            total_pausa_segundos += (
                fim_pausa - inicio_pausa
            ).total_seconds()

    return max(
        0,
        int(
            tempo_total_segundos
            - total_pausa_segundos
        ),
    )

def svc_process_expired_sessions(db: Session) -> None:
    agora = datetime.now(timezone.utc)

    sessoes_expiradas = find_expired_open_sessions(db, agora)

    for work_session in sessoes_expiradas:
        pausa = find_open_pause_by_session_id(
            db,
            work_session.id,
        )

        if pausa is not None:
            pausa.fim = work_session.expiracao

        work_session.saida = work_session.expiracao
        work_session.status = WorkSessionStatus.EXPIRADA_SISTEMA
        work_session.motivo_encerramento = (
            MotivoEncerramento.LIMITE_ATINGIDO
        )

        commit_expired_work_session(
            db,
            work_session,
            pausa,
        )

def svc_start_work_session(
    body: StartWorkSessionRequest,
    current_user: User,
    db: Session,
) -> WorkSessionItem:
    if current_user.role.nome in (
        RoleName.ADMIN,
        RoleName.SUPER_ADMIN,
    ):
        raise ForbiddenError(
            "Administradores não podem iniciar sessão de trabalho."
        )
    setor = find_sector_by_id(db, body.setor_id)
    if setor is None:
        raise NotFoundError("Setor não encontrado.")
    if not setor.ativo:
        raise ConflictError("O setor informado não está ativo.")
    vinculo = find_sector_user(db, setor.id, current_user.id) 
    if vinculo is None:
        raise ForbiddenError("Você não tem permissão para iniciar uma sessão neste setor.")
    sessao_aberta = find_open_session_by_user_id(db, current_user.id)
    if sessao_aberta:
        raise ConflictError("Você já possui uma sessão ativa.")
    
    agora = datetime.now(timezone.utc)
    work_session = WorkSession(
        usuario_id=current_user.id,
        setor_id=body.setor_id,
        entrada=agora,
        expiracao=agora + timedelta(hours=settings.WORK_SESSION_LIMIT_HOURS),
        status=WorkSessionStatus.ATIVA,
    )

    create_work_session(db, work_session)

    return WorkSessionItem(
        id=work_session.id,
        usuario_id=work_session.usuario_id,
        setor_id=work_session.setor_id,
        entrada_em=work_session.entrada,
        saida_em=work_session.saida,
        expira_em=work_session.expiracao,
        status=work_session.status,
        motivo_encerramento=work_session.motivo_encerramento,
        tempo_trabalhado_segundos=0,
    )

def svc_start_pause(
    session_id: UUID,
    current_user: User,
    db: Session,
) -> PauseItem:
    work_session = find_work_session_by_id(db, session_id)
    pausa = find_open_pause_by_session_id(db, session_id)

    if work_session is None:
        raise NotFoundError("Sessão de trabalho não encontrada.")

    if work_session.usuario_id != current_user.id:
        raise ForbiddenError(
            "Sessão não pertence ao usuário autenticado."
        )
    if pausa is not None:
        raise ConflictError(
            "Sessão já possui uma pausa ativa."
        )

    if work_session.status != WorkSessionStatus.ATIVA:
        raise ConflictError(
            "A sessão não está ativa e não pode iniciar uma pausa."
        )

    agora = datetime.now(timezone.utc)

    if agora >= work_session.expiracao:
        raise ConflictError(
            "Sessão expirada. Não é possível iniciar uma pausa."
        )

    work_session.status = WorkSessionStatus.EM_PAUSA

    nova_pausa = Pause(
        sessao_trabalho_id=work_session.id,
        inicio=agora,
    )

    commit_started_pause(
        db,
        work_session,
        nova_pausa,
    )   

    return PauseItem(
        id=nova_pausa.id,
        sessao_id=nova_pausa.sessao_trabalho_id,
        inicio_em=nova_pausa.inicio,
        fim_em=nova_pausa.fim,
    )

def svc_end_pause(
    session_id: UUID,
    pause_id: UUID,
    current_user: User,
    db: Session,
) -> PauseItem:
    work_session = find_work_session_by_id(db, session_id)

    if work_session is None:
        raise NotFoundError("Sessão de trabalho não encontrada.")

    if work_session.usuario_id != current_user.id:
        raise ForbiddenError(
            "Sessão não pertence ao usuário autenticado."
        )

    if work_session.status != WorkSessionStatus.EM_PAUSA:
        raise ConflictError(
            "Sessão não está em pausa."
        )

    pausa_aberta = find_pause_by_id(db, pause_id)

    if pausa_aberta is None:
        raise NotFoundError("Pausa não encontrada.")

    if pausa_aberta.sessao_trabalho_id != work_session.id:
        raise NotFoundError(
            "Pausa não pertence à sessão informada."
        )

    if pausa_aberta.fim is not None:
        raise ConflictError(
            "Pausa já foi encerrada."
        )

    agora = datetime.now(timezone.utc)

    if agora >= work_session.expiracao:
        raise ConflictError(
            "Sessão expirada. Não é possível encerrar a pausa manualmente."
        )

    pausa_aberta.fim = agora
    work_session.status = WorkSessionStatus.ATIVA

    commit_finished_pause(
        db,
        work_session,
        pausa_aberta,
    )

    return PauseItem(
        id=pausa_aberta.id,
        sessao_id=pausa_aberta.sessao_trabalho_id,
        inicio_em=pausa_aberta.inicio,
        fim_em=pausa_aberta.fim,
    )

def svc_end_work_session(
    session_id: UUID,
    current_user: User,
    db: Session,
) -> WorkSessionItem:
    work_session = find_work_session_by_id(
        db,
        session_id,
    )

    if work_session is None:
        raise NotFoundError(
            "Sessão de trabalho não encontrada."
        )

    if work_session.usuario_id != current_user.id:
        raise ForbiddenError(
            "Sessão não pertence ao usuário autenticado."
        )

    if work_session.status in (
        WorkSessionStatus.FINALIZADA,
        WorkSessionStatus.EXPIRADA_SISTEMA,
    ):
        raise ConflictError(
            "Sessão já foi encerrada."
        )

    agora = datetime.now(timezone.utc)
    pausa = None

    if agora >= work_session.expiracao:
        pausa = find_open_pause_by_session_id(
            db,
            work_session.id,
        )

        if pausa is not None:
            pausa.fim = work_session.expiracao

        work_session.saida = work_session.expiracao
        work_session.status = (
            WorkSessionStatus.EXPIRADA_SISTEMA
        )
        work_session.motivo_encerramento = (
            MotivoEncerramento.LIMITE_ATINGIDO
        )

        commit_expired_work_session(
            db,
            work_session,
            pausa,
        )

    else:
        if work_session.status == WorkSessionStatus.EM_PAUSA:
            pausa = find_open_pause_by_session_id(
                db,
                work_session.id,
            )

            if pausa is None:
                raise NotFoundError(
                    "Pausa aberta não encontrada."
                )

            pausa.fim = agora

        work_session.saida = agora
        work_session.status = WorkSessionStatus.FINALIZADA
        work_session.motivo_encerramento = (
            MotivoEncerramento.MANUAL
        )

        commit_finished_work_session(
            db,
            work_session,
            pausa,
        )

    return WorkSessionItem(
        id=work_session.id,
        usuario_id=work_session.usuario_id,
        setor_id=work_session.setor_id,
        entrada_em=work_session.entrada,
        saida_em=work_session.saida,
        expira_em=work_session.expiracao,
        status=work_session.status,
        motivo_encerramento=work_session.motivo_encerramento,
        tempo_trabalhado_segundos=_calculate_work_time(
            work_session,
            db,
        ),
    )

def svc_continue_work_session(
    session_id: UUID,
    current_user: User,
    db: Session,
) -> WorkSessionItem:
    work_session = find_work_session_by_id(
        db,
        session_id,
    )

    if work_session is None:
        raise NotFoundError(
            "Sessão de trabalho não encontrada."
        )

    if work_session.usuario_id != current_user.id:
        raise ForbiddenError(
            "Sessão não pertence ao usuário autenticado."
        )

    if work_session.status not in (
        WorkSessionStatus.ATIVA,
        WorkSessionStatus.EM_PAUSA,
    ):
        raise ConflictError(
            "Sessão não pode ser estendida."
        )

    agora = datetime.now(timezone.utc)

    if agora >= work_session.expiracao:
        raise ConflictError(
            "Sessão já atingiu o horário de expiração."
        )

    inicio_janela = (
        work_session.expiracao
        - timedelta(
            minutes=settings.WORK_SESSION_EXTENSION_WINDOW_MINUTES
        )
    )

    if agora < inicio_janela:
        raise ConflictError(
            "A sessão só pode ser prorrogada nos últimos "
            f"{settings.WORK_SESSION_EXTENSION_WINDOW_MINUTES} "
            "minutos antes da expiração."
        )

    work_session.expiracao += timedelta(
        hours=settings.WORK_SESSION_EXTENSION_HOURS
    )

    work_session = update_work_session(
        db,
        work_session,
    )

    return WorkSessionItem(
        id=work_session.id,
        usuario_id=work_session.usuario_id,
        setor_id=work_session.setor_id,
        entrada_em=work_session.entrada,
        saida_em=work_session.saida,
        expira_em=work_session.expiracao,
        status=work_session.status,
        motivo_encerramento=work_session.motivo_encerramento,
        tempo_trabalhado_segundos=_calculate_work_time(
            work_session,
            db,
        ),
    )

def svc_get_current_work_session(
    current_user: User,
    db: Session,
) -> CurrentWorkSessionResponse:
    work_session = find_open_session_by_user_id(
        db,
        current_user.id,
    )

    if work_session is None:
        return CurrentWorkSessionResponse(
            sessao=None,
        )

    pausas = list_pauses_by_session_id(
        db,
        work_session.id,
    )

    return CurrentWorkSessionResponse(
        sessao=WorkSessionDetail(
        id=work_session.id,
        usuario_id=work_session.usuario_id,
        setor_id=work_session.setor_id,
        entrada_em=work_session.entrada,
        saida_em=work_session.saida,
        expira_em=work_session.expiracao,
        status=work_session.status,
        motivo_encerramento=work_session.motivo_encerramento,
        tempo_trabalhado_segundos=_calculate_work_time(
            work_session,
            db,
        ),
        pausas=[
            PauseItem(
                id=pausa.id,
                sessao_id=pausa.sessao_trabalho_id,
                inicio_em=pausa.inicio,
                fim_em=pausa.fim,
            )
            for pausa in pausas
        ],
    ),
)

def svc_get_work_session(
    session_id: UUID,
    current_user: User,
    db: Session,
) -> WorkSessionDetail:
    work_session = find_work_session_by_id(
        db,
        session_id,
    )

    if work_session is None:
        raise NotFoundError(
            "Sessão de trabalho não encontrada."
        )

    if (
        work_session.usuario_id != current_user.id
        and current_user.role.nome not in (
            RoleName.ADMIN,
            RoleName.SUPER_ADMIN,
        )
    ):
        vinculo = find_sector_user(
            db,
            work_session.setor_id,
            current_user.id,
        )

        if vinculo is None or vinculo.papel != "lider":
            raise ForbiddenError(
                "Você não possui permissão para consultar esta sessão."
            )

    pausas = list_pauses_by_session_id(
        db,
        work_session.id,
    )

    return WorkSessionDetail(
        id=work_session.id,
        usuario_id=work_session.usuario_id,
        setor_id=work_session.setor_id,
        entrada_em=work_session.entrada,
        saida_em=work_session.saida,
        expira_em=work_session.expiracao,
        status=work_session.status,
        motivo_encerramento=work_session.motivo_encerramento,
        tempo_trabalhado_segundos=_calculate_work_time(
            work_session,
            db,
        ),
        pausas=[
            PauseItem(
                id=pausa.id,
                sessao_id=pausa.sessao_trabalho_id,
                inicio_em=pausa.inicio,
                fim_em=pausa.fim,
            )
            for pausa in pausas
        ],
    )

def svc_get_work_sessions(
    usuario_id: UUID | None,
    setor_id: UUID | None,
    inicio: datetime | None,
    fim: datetime | None,
    pagina: int,
    limite: int,
    current_user: User,
    db: Session,
) -> WorkSessionListResponse:
    if current_user.role.nome in (
        RoleName.ADMIN,
        RoleName.SUPER_ADMIN,
    ):
        usuario_consulta = usuario_id
    else:
        usuario_consulta = usuario_id or current_user.id

    if (
        usuario_consulta != current_user.id
        and current_user.role.nome not in (
            RoleName.ADMIN,
            RoleName.SUPER_ADMIN,
        )
    ):
        if setor_id is None:
            raise ForbiddenError(
                "Para consultar outro usuário, "
                "é necessário informar um setor que você lidera."
            )

        vinculo = find_sector_user(
            db,
            setor_id,
            current_user.id,
        )

        if vinculo is None or vinculo.papel != "lider":
            raise ForbiddenError(
                "Você não possui permissão para consultar "
                "as sessões deste usuário neste setor."
            )

    sessoes, total = list_work_sessions_paginated(
        db=db,
        pagina=pagina,
        limite=limite,
        usuario_id=usuario_consulta,
        setor_id=setor_id,
        inicio=inicio,
        fim=fim,
    )

    return WorkSessionListResponse(
        sessoes=[
            WorkSessionItem(
                id=work_session.id,
                usuario_id=work_session.usuario_id,
                setor_id=work_session.setor_id,
                entrada_em=work_session.entrada,
                saida_em=work_session.saida,
                expira_em=work_session.expiracao,
                status=work_session.status,
                motivo_encerramento=work_session.motivo_encerramento,
                tempo_trabalhado_segundos=_calculate_work_time(
                    work_session,
                    db,
                ),
            )
            for work_session in sessoes
        ],
        total=total,
        pagina=pagina,
        limite=limite,
    )

def svc_get_work_session_summary(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None,
    setor_id: UUID | None,
    current_user: User,
    db: Session,
) -> WorkSessionSummaryResponse:
    if inicio >= fim:
        raise BadRequestError(
            "O horário inicial deve ser anterior ao horário final."
        )

    if current_user.role.nome in (
        RoleName.ADMIN,
        RoleName.SUPER_ADMIN,
    ):
        usuario_consulta = usuario_id
    else:
        usuario_consulta = usuario_id or current_user.id

    if (
        usuario_consulta != current_user.id
        and current_user.role.nome not in (
            RoleName.ADMIN,
            RoleName.SUPER_ADMIN,
        )
    ):
        if setor_id is None:
            raise ForbiddenError(
                "Para consultar outro usuário, "
                "é necessário informar um setor que você lidera."
            )

        vinculo = find_sector_user(
            db,
            setor_id,
            current_user.id,
        )

        if vinculo is None or vinculo.papel != "lider":
            raise ForbiddenError(
                "Você não possui permissão para consultar "
                "este usuário neste setor."
            )

    sessoes = find_sessions_in_period(
        db=db,
        inicio=inicio,
        fim=fim,
        usuario_id=usuario_consulta,
        setor_id=setor_id,
    )

    tempo_total_segundos = 0

    for work_session in sessoes:
        tempo_total_segundos += _calculate_work_time_in_period(
            work_session,
            inicio,
            fim,
            db,
        )

    return WorkSessionSummaryResponse(
        usuario_id=usuario_consulta,
        setor_id=setor_id,
        inicio=inicio,
        fim=fim,
        tempo_trabalhado_segundos=tempo_total_segundos,
    )

def svc_get_metrics_summary(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None,
    setor_id: UUID | None,
    current_user: User,
    db: Session,
) -> MetricsSummaryResponse:
    _validate_metrics_access(current_user)

    if inicio >= fim:
        raise BadRequestError(
            "O horário inicial deve ser anterior ao horário final."
        )

    sessoes = find_sessions_in_period(
        db=db,
        inicio=inicio,
        fim=fim,
        usuario_id=usuario_id,
        setor_id=setor_id,
    )

    tempo_trabalhado_segundos = 0
    tempo_pausado_segundos = 0
    usuarios_com_tempo = set()

    for work_session in sessoes:
        tempo_trabalhado = _calculate_work_time_in_period(
            work_session,
            inicio,
            fim,
            db,
        )

        tempo_pausado = _calculate_pause_time_in_period(
            work_session,
            inicio,
            fim,
            db,
        )

        tempo_trabalhado_segundos += tempo_trabalhado
        tempo_pausado_segundos += tempo_pausado

        if tempo_trabalhado > 0:
            usuarios_com_tempo.add(
                work_session.usuario_id
            )

    sessoes_iniciadas = count_sessions_started_in_period(
        db=db,
        inicio=inicio,
        fim=fim,
        usuario_id=usuario_id,
        setor_id=setor_id,
    )

    return MetricsSummaryResponse(
        inicio=inicio,
        fim=fim,
        usuario_id=usuario_id,
        setor_id=setor_id,
        tempo_trabalhado_segundos=tempo_trabalhado_segundos,
        tempo_pausado_segundos=tempo_pausado_segundos,
        sessoes_iniciadas=sessoes_iniciadas,
        usuarios_com_tempo_trabalhado=len(
            usuarios_com_tempo
        ),
    )

def svc_get_metrics_users(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None,
    setor_id: UUID | None,
    pagina: int,
    limite: int,
    current_user: User,
    db: Session,
) -> MetricsUsersResponse:
    _validate_metrics_access(current_user)

    if inicio >= fim:
        raise BadRequestError(
            "O horário inicial deve ser anterior ao horário final."
        )

    if usuario_id is not None:
        sessoes = find_sessions_in_period(
            db=db,
            inicio=inicio,
            fim=fim,
            usuario_id=usuario_id,
            setor_id=setor_id,
        )

        usuarios = []

        if sessoes:
            usuario = sessoes[0].usuario
            usuarios.append(usuario)
    else:
        usuarios = list_users_with_sessions_in_period(
            db=db,
            inicio=inicio,
            fim=fim,
            setor_id=setor_id,
        )

    total = len(usuarios)

    inicio_pagina = (pagina - 1) * limite
    fim_pagina = inicio_pagina + limite

    usuarios_paginados = usuarios[
        inicio_pagina:fim_pagina
    ]

    itens = []

    for usuario in usuarios_paginados:
        sessoes = find_sessions_in_period(
            db=db,
            inicio=inicio,
            fim=fim,
            usuario_id=usuario.id,
            setor_id=setor_id,
        )

        tempo_trabalhado = 0
        tempo_pausado = 0

        for work_session in sessoes:
            tempo_trabalhado += _calculate_work_time_in_period(
                work_session,
                inicio,
                fim,
                db,
            )

            tempo_pausado += _calculate_pause_time_in_period(
                work_session,
                inicio,
                fim,
                db,
            )

        sessoes_iniciadas = count_sessions_started_in_period(
            db=db,
            inicio=inicio,
            fim=fim,
            usuario_id=usuario.id,
            setor_id=setor_id,
        )

        itens.append(
            MetricsUserItem(
                usuario_id=usuario.id,
                nome_completo=usuario.nome_completo,
                tempo_trabalhado_segundos=tempo_trabalhado,
                tempo_pausado_segundos=tempo_pausado,
                sessoes_iniciadas=sessoes_iniciadas,
            )
        )

    itens.sort(
        key=lambda item: str(item.usuario_id)
    )

    return MetricsUsersResponse(
        inicio=inicio,
        fim=fim,
        pagina=pagina,
        limite=limite,
        total=total,
        usuarios=itens,
    )

def svc_get_metrics_sectors(
    inicio: datetime,
    fim: datetime,
    usuario_id: UUID | None,
    setor_id: UUID | None,
    pagina: int,
    limite: int,
    current_user: User,
    db: Session,
) -> MetricsSectorsResponse:
    _validate_metrics_access(current_user)

    if inicio >= fim:
        raise BadRequestError(
            "O horário inicial deve ser anterior ao horário final."
        )

    if setor_id is not None:
        setor = find_sector_by_id(
            db,
            setor_id,
        )

        setores = [setor] if setor is not None else []
    else:
        setores = list_sectors_with_sessions_in_period(
            db=db,
            inicio=inicio,
            fim=fim,
            usuario_id=usuario_id,
        )

    total = len(setores)

    inicio_pagina = (pagina - 1) * limite
    fim_pagina = inicio_pagina + limite

    setores_paginados = setores[
        inicio_pagina:fim_pagina
    ]

    itens = []

    for setor in setores_paginados:
        sessoes = find_sessions_in_period(
            db=db,
            inicio=inicio,
            fim=fim,
            usuario_id=usuario_id,
            setor_id=setor.id,
        )

        tempo_trabalhado = 0
        tempo_pausado = 0
        usuarios_com_tempo = set()

        for work_session in sessoes:
            tempo = _calculate_work_time_in_period(
                work_session,
                inicio,
                fim,
                db,
            )

            tempo_trabalhado += tempo

            tempo_pausado += _calculate_pause_time_in_period(
                work_session,
                inicio,
                fim,
                db,
            )

            if tempo > 0:
                usuarios_com_tempo.add(
                    work_session.usuario_id
                )

        sessoes_iniciadas = count_sessions_started_in_period(
            db=db,
            inicio=inicio,
            fim=fim,
            usuario_id=usuario_id,
            setor_id=setor.id,
        )

        itens.append(
            MetricsSectorItem(
                setor_id=setor.id,
                setor_nome=setor.nome,
                tempo_trabalhado_segundos=tempo_trabalhado,
                tempo_pausado_segundos=tempo_pausado,
                sessoes_iniciadas=sessoes_iniciadas,
                usuarios_com_tempo_trabalhado=len(
                    usuarios_com_tempo
                ),
            )
        )

    itens.sort(
        key=lambda item: str(item.setor_id)
    )

    return MetricsSectorsResponse(
        inicio=inicio,
        fim=fim,
        pagina=pagina,
        limite=limite,
        total=total,
        setores=itens,
    )