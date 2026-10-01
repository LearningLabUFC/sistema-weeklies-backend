"""Schemas Pydantic para o módulo de Sessões de Trabalho."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.work_session import MotivoEncerramento, WorkSessionStatus

# ── Requests ─────────────────────────────────────────────────


class StartWorkSessionRequest(BaseModel):
    """Body para iniciar uma sessão de trabalho (POST /work-sessions)."""

    setor_id: UUID = Field(
        ...,
        description="UUID do setor em que o trabalho será realizado.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )


class CreateWorkSessionRequest(BaseModel):
    """Body para criação manual ou retroativa de sessão de trabalho."""

    usuario_id: UUID = Field(
        ...,
        description="UUID do usuário para o qual a sessão será criada.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    setor_id: UUID = Field(
        ...,
        description="UUID do setor em que o trabalho foi realizado.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    entrada: datetime = Field(
        ...,
        description="Data e hora de entrada da sessão.",
        examples=["2026-10-01T08:00:00Z"],
    )
    saida: datetime | None = Field(
        None,
        description="Data e hora de encerramento da sessão (opcional caso ainda em aberto).",
        examples=["2026-10-01T12:00:00Z"],
    )
    motivo_encerramento: MotivoEncerramento | None = Field(
        None,
        description="Motivo de encerramento da sessão.",
        examples=[MotivoEncerramento.MANUAL],
    )


class EndWorkSessionRequest(BaseModel):
    """Body para encerramento de sessão de trabalho (POST /work-sessions/{session_id}/end)."""

    motivo_encerramento: MotivoEncerramento = Field(
        default=MotivoEncerramento.MANUAL,
        description="Motivo do encerramento da sessão de trabalho.",
        examples=[MotivoEncerramento.MANUAL],
    )


class UpdateWorkSessionRequest(BaseModel):
    """Body para PATCH /work-sessions/{session_id}."""

    setor_id: UUID | None = Field(
        None,
        description="Novo UUID do setor associado à sessão.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    entrada: datetime | None = Field(
        None,
        description="Nova data e hora de entrada da sessão.",
        examples=["2026-10-01T08:00:00Z"],
    )
    saida: datetime | None = Field(
        None,
        description="Nova data e hora de saída da sessão.",
        examples=["2026-10-01T12:00:00Z"],
    )
    expiracao: datetime | None = Field(
        None,
        description="Nova data e hora limite de expiração da sessão.",
        examples=["2026-10-01T14:00:00Z"],
    )
    status: WorkSessionStatus | None = Field(
        None,
        description="Novo status da sessão de trabalho.",
        examples=[WorkSessionStatus.FINALIZADA],
    )
    motivo_encerramento: MotivoEncerramento | None = Field(
        None,
        description="Novo motivo de encerramento da sessão.",
        examples=[MotivoEncerramento.MANUAL],
    )


class StartPauseRequest(BaseModel):
    """Body para POST /work-sessions/{session_id}/pauses."""

    inicio: datetime | None = Field(
        None,
        description="Data e hora de início da pausa. Se omitido, utiliza o horário atual do servidor.",
        examples=["2026-10-01T12:00:00Z"],
    )


class EndPauseRequest(BaseModel):
    """Body para PATCH /work-sessions/{session_id}/pauses/{pause_id}/end."""

    fim: datetime | None = Field(
        None,
        description="Data e hora de término da pausa. Se omitido, utiliza o horário atual do servidor.",
        examples=["2026-10-01T12:30:00Z"],
    )


# ── Responses ────────────────────────────────────────────────


class PauseItem(BaseModel):
    """Representa um intervalo/pausa dentro de uma sessão de trabalho."""

    id: UUID = Field(
        ...,
        description="UUID identificador da pausa.",
        examples=["2fa85f64-5717-4562-b3fc-2c963f66afa2"],
    )
    sessao_trabalho_id: UUID = Field(
        ...,
        description="UUID da sessão de trabalho vinculada.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    inicio: datetime = Field(
        ...,
        description="Data e hora de início da pausa.",
        examples=["2026-10-01T12:00:00Z"],
    )
    fim: datetime | None = Field(
        None,
        description="Data e hora de encerramento da pausa (nulo se em andamento).",
        examples=["2026-10-01T12:30:00Z"],
    )
    duracao_segundos: int | None = Field(
        None,
        description="Duração da pausa em segundos.",
        examples=[1800],
    )
    duracao_minutos: float | None = Field(
        None,
        description="Duração da pausa em minutos.",
        examples=[30.0],
    )


class WorkSessionListItem(BaseModel):
    """Item da listagem de sessões de trabalho."""

    id: UUID = Field(
        ...,
        description="UUID da sessão de trabalho.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    usuario_id: UUID = Field(
        ...,
        description="UUID do usuário proprietário da sessão.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    usuario_nome: str | None = Field(
        None,
        description="Nome completo do usuário (resolvido da relação).",
        examples=["João Silva"],
    )
    setor_id: UUID = Field(
        ...,
        description="UUID do setor onde a sessão foi realizada.",
        examples=["5fa85f64-5717-4562-b3fc-2c963f66afa2"],
    )
    setor_nome: str | None = Field(
        None,
        description="Nome do setor (resolvido da relação).",
        examples=["Desenvolvimento"],
    )
    entrada: datetime = Field(
        ...,
        description="Data e hora de início da sessão.",
        examples=["2026-10-01T08:00:00Z"],
    )
    saida: datetime | None = Field(
        None,
        description="Data e hora de encerramento da sessão.",
        examples=["2026-10-01T12:00:00Z"],
    )
    expiracao: datetime | None = Field(
        None,
        description="Data e hora prevista para expiração automática.",
        examples=["2026-10-01T14:00:00Z"],
    )
    status: WorkSessionStatus = Field(
        ...,
        description="Status atual da sessão de trabalho.",
        examples=[WorkSessionStatus.ATIVA],
    )
    motivo_encerramento: MotivoEncerramento | None = Field(
        None,
        description="Motivo do encerramento da sessão.",
        examples=[MotivoEncerramento.MANUAL],
    )
    total_pausas: int = Field(
        0,
        description="Quantidade total de pausas nesta sessão.",
        examples=[1],
    )
    duracao_total_segundos: int | None = Field(
        None,
        description="Duração líquida total trabalhada em segundos (descontando pausas).",
        examples=[12600],
    )
    duracao_total_minutos: float | None = Field(
        None,
        description="Duração líquida total trabalhada em minutos (descontando pausas).",
        examples=[210.0],
    )


class WorkSessionDetail(BaseModel):
    """Detalhamento completo de uma sessão de trabalho, incluindo suas pausas."""

    id: UUID = Field(
        ...,
        description="UUID da sessão de trabalho.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    usuario_id: UUID = Field(
        ...,
        description="UUID do usuário proprietário da sessão.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    usuario_nome: str | None = Field(
        None,
        description="Nome completo do usuário (resolvido da relação).",
        examples=["João Silva"],
    )
    setor_id: UUID = Field(
        ...,
        description="UUID do setor onde a sessão foi realizada.",
        examples=["5fa85f64-5717-4562-b3fc-2c963f66afa2"],
    )
    setor_nome: str | None = Field(
        None,
        description="Nome do setor (resolvido da relação).",
        examples=["Desenvolvimento"],
    )
    entrada: datetime = Field(
        ...,
        description="Data e hora de início da sessão.",
        examples=["2026-10-01T08:00:00Z"],
    )
    saida: datetime | None = Field(
        None,
        description="Data e hora de encerramento da sessão.",
        examples=["2026-10-01T12:00:00Z"],
    )
    expiracao: datetime | None = Field(
        None,
        description="Data e hora limite de expiração automática.",
        examples=["2026-10-01T14:00:00Z"],
    )
    status: WorkSessionStatus = Field(
        ...,
        description="Status atual da sessão de trabalho.",
        examples=[WorkSessionStatus.ATIVA],
    )
    motivo_encerramento: MotivoEncerramento | None = Field(
        None,
        description="Motivo do encerramento da sessão.",
        examples=[MotivoEncerramento.MANUAL],
    )
    pausas: list[PauseItem] = Field(
        default_factory=list,
        description="Lista de pausas registradas nesta sessão.",
    )
    duracao_total_segundos: int | None = Field(
        None,
        description="Duração líquida total trabalhada em segundos (descontando pausas).",
        examples=[12600],
    )
    duracao_total_minutos: float | None = Field(
        None,
        description="Duração líquida total trabalhada em minutos (descontando pausas).",
        examples=[210.0],
    )


class WorkSessionListResponse(BaseModel):
    """Resposta paginada para GET /work-sessions."""

    sessoes: list[WorkSessionListItem] = Field(
        ...,
        description="Lista de sessões de trabalho na página atual.",
    )
    total: int = Field(
        ...,
        description="Número total de sessões encontradas.",
        examples=[10],
    )
    pagina: int = Field(
        ...,
        description="Página atual (1-indexed).",
        examples=[1],
    )
    limite: int = Field(
        ...,
        description="Quantidade de itens por página.",
        examples=[20],
    )


class CurrentWorkSessionResponse(BaseModel):
    """Resposta para consulta do estado da sessão ativa do usuário."""

    ativa: bool = Field(
        ...,
        description="Indica se o usuário possui uma sessão ativa no momento.",
        examples=[True],
    )
    em_pausa: bool = Field(
        ...,
        description="Indica se a sessão atual está pausada no momento.",
        examples=[False],
    )
    sessao: WorkSessionDetail | None = Field(
        None,
        description="Dados detalhados da sessão ativa, se houver.",
    )
    pausa_atual: PauseItem | None = Field(
        None,
        description="Dados da pausa atualmente em andamento, se houver.",
    )


class WorkSessionResponse(BaseModel):
    """Resposta com mensagem e dados da sessão de trabalho."""

    mensagem: str = Field(
        ...,
        examples=["Sessão de trabalho iniciada com sucesso."],
    )
    sessao: WorkSessionDetail


class PauseResponse(BaseModel):
    """Resposta com mensagem e dados da pausa."""

    mensagem: str = Field(
        ...,
        examples=["Pausa iniciada com sucesso."],
    )
    pausa: PauseItem
