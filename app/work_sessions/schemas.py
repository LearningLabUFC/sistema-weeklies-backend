"""Schemas Pydantic para o módulo de Sessões de Trabalho."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.work_session import MotivoEncerramento, WorkSessionStatus

# ── Requests ─────────────────────────────────────────────────


class StartWorkSessionRequest(BaseModel):
    """Body para POST /work-sessions."""

    setor_id: UUID = Field(
        ...,
        description="UUID do setor em que o trabalho será realizado.",
        examples=["44444444-4444-4444-8444-444444444444"],
    )

# ── Itens ─────────────────────────────────────────────────

class PauseItem(BaseModel):
    """Representa uma pausa vinculada a uma sessão de trabalho."""

    id: UUID = Field(
        ...,
        description="UUID da pausa.",
        examples=["33333333-3333-4333-8333-333333333333"],
    )

    sessao_id: UUID = Field(
        ...,
        description="UUID da sessão de trabalho vinculada.",
        examples=["11111111-1111-4111-8111-111111111111"],
    )

    inicio_em: datetime = Field(
        ...,
        description="Data e hora de início da pausa.",
        examples=["2026-09-26T13:00:00Z"],
    )

    fim_em: datetime | None = Field(
        None,
        description=(
            "Data e hora de encerramento da pausa. "
            "Nulo enquanto a pausa estiver aberta."
        ),
        examples=["2026-09-26T13:30:00Z"],
    )


class WorkSessionItem(BaseModel):
    """Representação básica de uma sessão de trabalho."""

    id: UUID = Field(
        ...,
        description="UUID da sessão de trabalho.",
        examples=["11111111-1111-4111-8111-111111111111"],
    )

    usuario_id: UUID = Field(
        ...,
        description="UUID do usuário proprietário da sessão.",
        examples=["22222222-2222-4222-8222-222222222222"],
    )

    setor_id: UUID = Field(
        ...,
        description="UUID do setor em que o trabalho foi realizado.",
        examples=["44444444-4444-4444-8444-444444444444"],
    )

    entrada_em: datetime = Field(
        ...,
        description="Data e hora de início da sessão.",
        examples=["2026-09-26T11:00:00Z"],
    )

    saida_em: datetime | None = Field(
        None,
        description=(
            "Data e hora de encerramento da sessão. "
            "Nulo enquanto estiver aberta."
        ),
        examples=["2026-09-26T15:00:00Z"],
    )

    expira_em: datetime = Field(
        ...,
        description=(
            "Data e hora limite para encerramento automático da sessão. "
            "Pode ser prorrogada quando o usuário confirma que continua trabalhando."
        ),
        examples=["2026-09-26T19:00:00Z"],
    )

    status: WorkSessionStatus = Field(
        ...,
        description="Status atual da sessão de trabalho.",
        examples=[WorkSessionStatus.ATIVA],
    )

    motivo_encerramento: MotivoEncerramento | None = Field(
        None,
        description=(
            "Motivo do encerramento da sessão. "
            "Permanece nulo enquanto a sessão estiver aberta."
        ),
        examples=[MotivoEncerramento.MANUAL],
    )

    tempo_trabalhado_segundos: int = Field(
        ...,
        description=(
            "Tempo líquido trabalhado em segundos, calculado pelo Service "
            "e descontando as pausas."
        ),
        examples=[12600],
    )


class WorkSessionDetail(WorkSessionItem):
    """Detalhamento completo da sessão, incluindo suas pausas."""

    pausas: list[PauseItem] = Field(
        default_factory=list,
        description="Lista de pausas registradas na sessão.",
    )


class MetricsUserItem(BaseModel):
    """Métricas agrupadas por usuário."""

    usuario_id: UUID = Field(
        ...,
        description="UUID do usuário.",
        examples=["22222222-2222-4222-8222-222222222222"],
    )

    nome_completo: str = Field(
        ...,
        description="Nome completo do usuário.",
        examples=["Usuário de exemplo"],
    )

    tempo_trabalhado_segundos: int = Field(
        ...,
        description="Tempo total trabalhado pelo usuário no período.",
        examples=[12600],
    )

    tempo_pausado_segundos: int = Field(
        ...,
        description="Tempo total em pausas do usuário no período.",
        examples=[1800],
    )

    sessoes_iniciadas: int = Field(
        ...,
        description="Quantidade de sessões iniciadas pelo usuário no período.",
        examples=[1],
    )

class MetricsSectorItem(BaseModel):
    """Métricas agrupadas por setor."""

    setor_id: UUID = Field(
        ...,
        description="UUID do setor.",
        examples=["44444444-4444-4444-8444-444444444444"],
    )

    setor_nome: str = Field(
        ...,
        description="Nome atual do setor.",
        examples=["Setor de exemplo"],
    )

    tempo_trabalhado_segundos: int = Field(
        ...,
        description="Tempo total trabalhado no setor.",
        examples=[12600],
    )

    tempo_pausado_segundos: int = Field(
        ...,
        description="Tempo total em pausas no setor.",
        examples=[1800],
    )

    sessoes_iniciadas: int = Field(
        ...,
        description="Quantidade de sessões iniciadas no setor.",
        examples=[1],
    )

    usuarios_com_tempo_trabalhado: int = Field(
        ...,
        description=(
            "Quantidade de usuários distintos com tempo trabalhado no setor."
        ),
        examples=[1],
    )

class TimelineIntervalItem(BaseModel):
    """Intervalo individual da timeline de métricas."""

    inicio: datetime = Field(
        ...,
        description="Início do intervalo.",
    )

    fim: datetime = Field(
        ...,
        description="Fim do intervalo.",
    )

    tempo_trabalhado_segundos: int = Field(
        ...,
        description="Tempo trabalhado dentro do intervalo.",
        examples=[12600],
    )

    tempo_pausado_segundos: int = Field(
        ...,
        description="Tempo em pausas dentro do intervalo.",
        examples=[1800],
    )


# ── Response ─────────────────────────────────────────────────

class CurrentWorkSessionResponse(BaseModel):
    """Resposta para GET /work-sessions/current."""

    sessao: WorkSessionDetail | None = Field(
        None,
        description=(
            "Sessão atualmente aberta do usuário. "
            "Retorna nulo quando não existir sessão aberta válida."
        ),
    )

class WorkSessionListResponse(BaseModel):
    """Resposta paginada para GET /work-sessions."""

    sessoes: list[WorkSessionItem] = Field(
        default_factory=list,
        description="Lista de sessões encontradas.",
    )

    total: int = Field(
        ...,
        description=(
            "Quantidade total de sessões encontradas antes da paginação."
        ),
        examples=[87],
    )

    pagina: int = Field(
        ...,
        description="Página atual da listagem.",
        examples=[1],
    )

    limite: int = Field(
        ...,
        description="Quantidade máxima de registros por página.",
        examples=[20],
    )

class WorkSessionSummaryResponse(BaseModel):
    """Resposta para GET /work-sessions/summary."""

    usuario_id: UUID | None = Field(
    None,
    description=(
        "UUID do usuário consultado. "
        "Nulo quando o resumo considera todos os usuários."
    ),
    examples=["22222222-2222-4222-8222-222222222222"],
)

    setor_id: UUID | None = Field(
        None,
        description=(
            "UUID do setor filtrado. "
            "Nulo quando todos os setores permitidos são considerados."
        ),
        examples=["44444444-4444-4444-8444-444444444444"],
    )

    inicio: datetime = Field(
        ...,
        description="Início do período consultado.",
        examples=["2026-09-26T00:00:00Z"],
    )

    fim: datetime = Field(
        ...,
        description="Fim do período consultado.",
        examples=["2026-09-27T00:00:00Z"],
    )

    tempo_trabalhado_segundos: int = Field(
        ...,
        description="Tempo líquido trabalhado dentro do período consultado.",
        examples=[12600],
    )


class MetricsSummaryResponse(BaseModel):
    """Resposta para GET /work-sessions/metrics/summary."""

    inicio: datetime = Field(
        ...,
        description="Início do período consultado.",
        examples=["2026-09-26T00:00:00Z"],
    )

    fim: datetime = Field(
        ...,
        description="Fim do período consultado.",
        examples=["2026-09-27T00:00:00Z"],
    )

    usuario_id: UUID | None = Field(
        None,
        description="UUID do usuário filtrado, quando informado.",
    )

    setor_id: UUID | None = Field(
        None,
        description="UUID do setor filtrado, quando informado.",
    )

    tempo_trabalhado_segundos: int = Field(
        ...,
        description="Tempo total trabalhado no período.",
        examples=[288000],
    )

    tempo_pausado_segundos: int = Field(
        ...,
        description="Tempo total em pausas no período.",
        examples=[18000],
    )

    sessoes_iniciadas: int = Field(
        ...,
        description="Quantidade de sessões iniciadas no período.",
        examples=[20],
    )

    usuarios_com_tempo_trabalhado: int = Field(
        ...,
        description=(
            "Quantidade de usuários distintos com tempo trabalhado "
            "maior que zero."
        ),
        examples=[8],
    )


class MetricsUsersResponse(BaseModel):
    """Resposta para GET /work-sessions/metrics/users."""

    inicio: datetime = Field(
        ...,
        description="Início do período consultado.",
    )

    fim: datetime = Field(
        ...,
        description="Fim do período consultado.",
    )

    pagina: int = Field(
        ...,
        description="Página atual.",
        examples=[1],
    )

    limite: int = Field(
        ...,
        description="Quantidade máxima de registros por página.",
        examples=[20],
    )

    total: int = Field(
        ...,
        description="Quantidade total de usuários antes da paginação.",
        examples=[1],
    )

    usuarios: list[MetricsUserItem] = Field(
        default_factory=list,
        description="Métricas agrupadas por usuário.",
    )

class MetricsSectorsResponse(BaseModel):
    """Resposta para GET /work-sessions/metrics/sectors."""

    inicio: datetime = Field(
        ...,
        description="Início do período consultado.",
    )

    fim: datetime = Field(
        ...,
        description="Fim do período consultado.",
    )

    pagina: int = Field(
        ...,
        description="Página atual.",
        examples=[1],
    )

    limite: int = Field(
        ...,
        description="Quantidade máxima de registros por página.",
        examples=[20],
    )

    total: int = Field(
        ...,
        description="Quantidade total de setores antes da paginação.",
        examples=[1],
    )

    setores: list[MetricsSectorItem] = Field(
        default_factory=list,
        description="Métricas agrupadas por setor.",
    )

class MetricsTimelineResponse(BaseModel):
    """Resposta para GET /work-sessions/metrics/timeline."""

    inicio: datetime = Field(
        ...,
        description="Início do período solicitado.",
    )

    fim: datetime = Field(
        ...,
        description="Fim do período solicitado.",
    )

    agrupamento: str = Field(
        ...,
        description="Agrupamento utilizado: dia, semana ou mes.",
        examples=["dia"],
    )

    fuso: str = Field(
        ...,
        description="Fuso horário utilizado no agrupamento.",
        examples=["America/Sao_Paulo"],
    )

    intervalos: list[TimelineIntervalItem] = Field(
        default_factory=list,
        description="Intervalos cronológicos da timeline.",
    )