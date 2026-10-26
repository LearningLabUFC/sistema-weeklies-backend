"""Schemas Pydantic para o módulo de Weeklies — CRUD de Tasks e Ciclo de Vida de Weeklies."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Tasks Requests ───────────────────────────────────────────


class CreateTaskRequest(BaseModel):
    """Body para POST /tasks."""

    setor_id: UUID = Field(
        ...,
        description="UUID do setor ao qual a task pertence.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    titulo: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Título da task.",
        examples=["Implementar tela de login"],
    )
    descricao: str | None = Field(
        None,
        description="Descrição detalhada da task.",
        examples=["Criar componente React com validação de formulário."],
    )
    prazo_conclusao: date | None = Field(
        None,
        description=(
            "Data limite para conclusão. "
            "Se não informado, será criado_em + 14 dias (definido no backend)."
        ),
        examples=["2026-10-14"],
    )

    @field_validator("titulo")
    @classmethod
    def validar_titulo(cls, v: str) -> str:
        v_strip = v.strip()
        if not v_strip:
            raise ValueError("O título da task não pode ser vazio ou conter apenas espaços em branco.")
        return v_strip


class UpdateTaskRequest(BaseModel):
    """Body para PATCH /tasks/{task_id}. Campos explicitamente permitidos."""

    titulo: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Novo título da task.",
        examples=["Implementar tela de cadastro"],
    )
    descricao: str | None = Field(
        None,
        description="Nova descrição da task.",
        examples=["Incluir validação de CPF no formulário."],
    )

    @field_validator("titulo")
    @classmethod
    def validar_titulo(cls, v: str | None) -> str | None:
        if v is not None:
            v_strip = v.strip()
            if not v_strip:
                raise ValueError("O título da task não pode ser vazio ou conter apenas espaços em branco.")
            return v_strip
        return v


class UpdateTaskPrazoRequest(BaseModel):
    """Body para PATCH /tasks/{task_id}/prazo. Uso exclusivo do líder."""

    prazo_conclusao: date = Field(
        ...,
        description="Novo prazo de conclusão da task.",
        examples=["2026-10-28"],
    )


# ── Tasks Responses ──────────────────────────────────────────


class TaskResponse(BaseModel):
    """Representação pública de uma task."""

    id: UUID = Field(..., description="UUID da task.")
    usuario_id: UUID = Field(..., description="UUID do dono da task.")
    setor_id: UUID = Field(..., description="UUID do setor.")
    origem_task_id: UUID | None = Field(
        None,
        description="UUID da task original (quando clonada por atribuição).",
    )
    titulo: str = Field(..., description="Título da task.")
    descricao: str | None = Field(None, description="Descrição da task.")
    status: str = Field(
        ...,
        description="Status atual: PENDENTE, CONCLUIDA, EM_AUDITORIA, REMOVIDA_PELO_LIDER.",
        examples=["PENDENTE"],
    )
    prazo_conclusao: date | None = Field(
        None, description="Data limite para conclusão."
    )
    entrada_auditoria_em: datetime | None = Field(
        None,
        description="Quando a task entrou em auditoria.",
    )
    criado_em: datetime = Field(..., description="Data de criação.")
    atualizado_em: datetime = Field(..., description="Data da última atualização.")

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """Resposta paginada para GET /tasks/me."""

    tasks: list[TaskResponse] = Field(
        ..., description="Lista de tasks na página atual."
    )
    total: int = Field(..., description="Número total de tasks.", examples=[10])
    pagina: int = Field(..., description="Página atual (1-indexed).", examples=[1])
    limite: int = Field(
        ..., description="Quantidade de itens por página.", examples=[20]
    )


# ── Weekly Tasks Requests & Responses ─────────────────────────


class AddWeeklyTaskRequest(BaseModel):
    """
    Body para POST /weeklies/{weekly_id}/tasks.
    Permite vincular uma task já existente via task_id OU criar uma task nova inline via titulo.
    """

    task_id: UUID | None = Field(
        None,
        description="UUID de uma task existente que pertença ao mesmo usuário e setor.",
    )
    titulo: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Título da nova task criada diretamente na weekly.",
    )
    descricao: str | None = Field(
        None,
        description="Descrição detalhada da task quando criada inline.",
    )
    prazo_conclusao: date | None = Field(
        None,
        description="Prazo de conclusão da task (se criada inline).",
    )

    @field_validator("titulo")
    @classmethod
    def validar_titulo(cls, v: str | None) -> str | None:
        if v is not None:
            v_strip = v.strip()
            if not v_strip:
                raise ValueError("O título da task não pode ser vazio ou conter apenas espaços em branco.")
            return v_strip
        return v

    @model_validator(mode="after")
    def validar_origem(self) -> "AddWeeklyTaskRequest":
        if not self.task_id and not self.titulo:
            raise ValueError(
                "Informe 'task_id' para vincular uma task existente ou 'titulo' para criar uma nova."
            )
        return self


class UpdateWeeklyTaskRequest(BaseModel):
    """Body para PATCH /weeklies/{weekly_id}/tasks/{weekly_task_id}."""

    concluida: bool | None = Field(
        None,
        description="Se a task foi concluída no escopo deste relatório semanal.",
    )
    impedimento: str | None = Field(
        None,
        description="Descrição de eventual impedimento encontrado pelo membro.",
    )


class WeeklyTaskItemResponse(BaseModel):
    """Item associativo de task dentro de uma weekly."""

    id: UUID = Field(..., description="UUID do vínculo weekly_task.")
    task_id: UUID = Field(..., description="UUID da task.")
    titulo: str = Field(..., description="Título da task.")
    descricao: str | None = Field(None, description="Descrição da task.")
    status_task: str = Field(..., description="Status global da task.")
    prazo_conclusao: date | None = Field(
        None, description="Prazo de conclusão da task."
    )
    concluida: bool = Field(
        ..., description="Indicador se a tarefa foi concluída nesta semana."
    )
    impedimento: str | None = Field(
        None, description="Impedimento relatado nesta semana."
    )
    posicao: int = Field(..., description="Posição de ordenação no card.")
    origem: str = Field(
        ...,
        description="Origem da task na weekly: NOVA ou HERDADA.",
        examples=["NOVA"],
    )

    model_config = {"from_attributes": True}


# ── Weeklies Requests & Responses ─────────────────────────────


class CreateWeeklyRequest(BaseModel):
    """Body para POST /weeklies."""

    setor_id: UUID = Field(
        ...,
        description="UUID do setor ao qual o relatório semanal pertence.",
    )
    semana_referencia: date | None = Field(
        None,
        description=(
            "Segunda-feira de fechamento da semana de referência. "
            "Deve corresponder à janela aberta. Se omitido, será calculada "
            "automaticamente pela janela atual."
        ),
    )


class WeeklyResponse(BaseModel):
    """Detalhes completos de uma weekly com suas tarefas."""

    id: UUID = Field(..., description="UUID da weekly.")
    usuario_id: UUID = Field(..., description="UUID do membro.")
    membro_nome: str | None = Field(None, description="Nome do membro dono da weekly.")
    setor_id: UUID = Field(..., description="UUID do setor.")
    semana_referencia: date = Field(
        ..., description="Data da segunda-feira de fechamento."
    )
    status: str = Field(
        ...,
        description="Status: RASCUNHO, ENVIADA, APROVADA, REJEITADA, EXPIRADA.",
        examples=["RASCUNHO"],
    )
    enviada_em: datetime | None = Field(
        None, description="Data/hora de submissão pelo membro."
    )
    avaliada_em: datetime | None = Field(
        None, description="Data/hora de avaliação pelo líder."
    )
    avaliada_por: UUID | None = Field(
        None, description="UUID do líder/admin que avaliou."
    )
    observacao_lider: str | None = Field(
        None, description="Observação ou feedback do líder."
    )
    motivo_expiracao: str | None = Field(
        None, description="Motivo pelo qual a weekly expirou (ex: OMISSAO_LIDERANCA, CORRECAO_NAO_ENVIADA)."
    )
    detalhe_expiracao: str | None = Field(
        None, description="Detalhamento textual do motivo de expiração."
    )
    criado_em: datetime = Field(..., description="Data de criação.")
    atualizado_em: datetime = Field(..., description="Data da última alteração.")
    tasks: list[WeeklyTaskItemResponse] = Field(
        default_factory=list,
        description="Tarefas associadas a esta weekly.",
    )

    model_config = {"from_attributes": True}


class WeeklySummaryResponse(BaseModel):
    """Resumo de uma weekly para listagem."""

    id: UUID = Field(..., description="UUID da weekly.")
    usuario_id: UUID = Field(..., description="UUID do membro.")
    membro_nome: str | None = Field(None, description="Nome do membro dono da weekly.")
    setor_id: UUID = Field(..., description="UUID do setor.")
    semana_referencia: date = Field(
        ..., description="Data da segunda-feira de fechamento."
    )
    status: str = Field(..., description="Status atual da weekly.")
    enviada_em: datetime | None = Field(
        None, description="Data/hora de submissão."
    )
    total_tasks: int = Field(0, description="Total de tarefas nesta weekly.")
    total_concluidas: int = Field(
        0, description="Total de tarefas marcadas como concluídas."
    )
    total_impedimentos: int = Field(
        0, description="Total de tarefas com impedimento relatado."
    )
    motivo_expiracao: str | None = Field(
        None, description="Motivo pelo qual a weekly expirou."
    )
    criado_em: datetime = Field(..., description="Data de criação.")

    model_config = {"from_attributes": True}


class EvaluateWeeklyRequest(BaseModel):
    """Body para PATCH /weeklies/{weekly_id}/avaliar."""

    status: Literal["APROVADA", "REJEITADA"] = Field(
        ...,
        description="Novo status: APROVADA ou REJEITADA.",
        examples=["APROVADA"],
    )
    observacao_lider: str | None = Field(
        None,
        description="Feedback do líder (obrigatório se REJEITADA, opcional se APROVADA).",
        examples=["Ótimo trabalho nesta semana!"],
    )


class WeeklyListResponse(BaseModel):
    """Resposta paginada para GET /weeklies/me."""

    weeklies: list[WeeklySummaryResponse] = Field(
        ..., description="Lista de resumos de weeklies."
    )
    total: int = Field(..., description="Total de weeklies encontradas.")
    pagina: int = Field(..., description="Página atual (1-indexed).")
    limite: int = Field(..., description="Itens por página.")


# ── Advertências Requests & Responses (Fase 7) ───────────────


class WeeklyWarningResponse(BaseModel):
    """Representação pública de uma advertência de weekly."""

    id: UUID = Field(..., description="UUID da advertência.")
    usuario_id: UUID = Field(..., description="UUID do membro advertido.")
    usuario_nome: str | None = Field(None, description="Nome completo do membro.")
    setor_id: UUID = Field(..., description="UUID do setor.")
    setor_nome: str | None = Field(None, description="Nome do setor.")
    tipo: str = Field(
        ...,
        description="Tipo de advertência: 1a_ADVERTENCIA, 2a_ADVERTENCIA ou DESLIGAMENTO.",
        examples=["1a_ADVERTENCIA"],
    )
    semana_referencia: date = Field(..., description="Segunda-feira de referência.")
    semanas_ausentes: int = Field(
        ..., description="Total de semanas consecutivas sem envio."
    )
    criado_em: datetime = Field(..., description="Data de emissão da advertência.")

    model_config = {"from_attributes": True}


class WeeklyWarningListResponse(BaseModel):
    """Resposta paginada para listagem de advertências."""

    advertencias: list[WeeklyWarningResponse] = Field(
        ..., description="Lista de advertências da página atual."
    )
    total: int = Field(..., description="Total de advertências encontradas.")
    pagina: int = Field(..., description="Página atual (1-indexed).")
    limite: int = Field(..., description="Itens por página.")


# ── Atribuição de Tasks Requests & Responses (Fase 9) ────────


class CreateTaskAssignmentRequest(BaseModel):
    """Body para POST /tasks/{task_id}/atribuir."""

    atribuido_id: UUID = Field(
        ...,
        description="UUID do membro convidado a colaborar na task.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )


class TaskAssignmentResponse(BaseModel):
    """Representação pública de uma solicitação de atribuição/convite de task."""

    id: UUID = Field(..., description="UUID da atribuição.")
    task_id: UUID = Field(..., description="UUID da task de origem.")
    task_titulo: str | None = Field(None, description="Título da task.")
    solicitante_id: UUID = Field(..., description="UUID de quem enviou o convite.")
    solicitante_nome: str | None = Field(None, description="Nome de quem enviou o convite.")
    atribuido_id: UUID = Field(..., description="UUID do membro convidado.")
    atribuido_nome: str | None = Field(None, description="Nome do membro convidado.")
    status: str = Field(
        ...,
        description="Status do convite: PENDENTE, ACEITA, RECUSADA ou EXPIRADA.",
        examples=["PENDENTE"],
    )
    criado_em: datetime = Field(..., description="Data de envio do convite.")
    respondido_em: datetime | None = Field(
        None, description="Data em que o convite foi aceito ou recusado."
    )

    model_config = {"from_attributes": True}


class TaskAssignmentListResponse(BaseModel):
    """Resposta paginada para listagem de convites de task."""

    atribuicoes: list[TaskAssignmentResponse] = Field(
        ..., description="Lista de convites da página atual."
    )
    total: int = Field(..., description="Total de convites encontrados.")
    pagina: int = Field(..., description="Página atual (1-indexed).")
    limite: int = Field(..., description="Itens por página.")


class ColaboradorElegivelItem(BaseModel):
    """Representação simplificada de membro elegível para receber tarefas."""

    id: UUID = Field(..., description="UUID do colaborador.")
    nome_completo: str = Field(..., description="Nome completo do colaborador.")
    email: str = Field(..., description="E-mail do colaborador.")
    matricula: str = Field(..., description="Matrícula institucional do colaborador.")
    setores: list[str] = Field(
        default_factory=list,
        description="Lista de nomes dos setores aos quais o colaborador pertence.",
    )


class ColaboradoresElegiveisResponse(BaseModel):
    """Resposta paginada de colaboradores elegíveis para tarefas."""

    colaboradores: list[ColaboradorElegivelItem] = Field(
        ..., description="Lista de colaboradores da página atual."
    )
    total: int = Field(..., description="Total de colaboradores encontrados.")
    pagina: int = Field(..., description="Página atual (1-indexed).")
    limite: int = Field(..., description="Itens por página.")


# ── Dashboard Requests & Responses (Fase 11) ─────────────────


class SectorDashboardResponse(BaseModel):
    """Métricas consolidadas de um setor para a semana de referência."""

    setor_id: UUID = Field(..., description="UUID do setor.")
    setor_nome: str = Field(..., description="Nome do setor.")
    semana_referencia: date = Field(..., description="Segunda-feira de referência.")
    total_membros: int = Field(..., description="Total de membros ativos no setor.")
    weeklies_enviadas: int = Field(
        ..., description="Total de weeklies enviadas aguardando avaliação."
    )
    weeklies_aprovadas: int = Field(..., description="Total de weeklies aprovadas.")
    weeklies_rejeitadas: int = Field(..., description="Total de weeklies rejeitadas.")
    weeklies_expiradas: int = Field(0, description="Total de weeklies expiradas no setor.")
    weeklies_rascunho: int = Field(
        ..., description="Total de weeklies em rascunho / não enviadas."
    )
    taxa_submissao_percentual: float = Field(
        ..., description="Taxa de submissão percentual dos membros ativos."
    )
    total_tasks: int = Field(..., description="Total de tarefas da semana no setor.")
    tasks_concluidas: int = Field(..., description="Total de tarefas concluídas nesta semana.")
    tasks_pendentes: int = Field(..., description="Total de tarefas pendentes no setor.")
    tasks_em_auditoria: int = Field(
        ..., description="Total de tarefas sob auditoria no setor."
    )
    total_impedimentos: int = Field(
        ..., description="Total de impedimentos relatados nesta semana."
    )

    model_config = {"from_attributes": True}


class GlobalDashboardResponse(BaseModel):
    """Métricas consolidadas de todos os setores para a semana de referência (Admin)."""

    semana_referencia: date = Field(..., description="Segunda-feira de referência.")
    total_setores: int = Field(..., description="Total de setores ativos.")
    total_membros: int = Field(
        ..., description="Total de membros ativos em todos os setores."
    )
    total_weeklies_enviadas: int = Field(..., description="Total geral de weeklies enviadas.")
    total_weeklies_aprovadas: int = Field(..., description="Total geral de weeklies aprovadas.")
    total_weeklies_rejeitadas: int = Field(..., description="Total geral de weeklies rejeitadas.")
    total_weeklies_expiradas: int = Field(0, description="Total geral de weeklies expiradas.")
    total_weeklies_rascunho: int = Field(..., description="Total geral de weeklies em rascunho.")
    taxa_submissao_geral_percentual: float = Field(
        ..., description="Taxa de submissão geral consolidada."
    )
    total_tasks_em_auditoria: int = Field(
        ..., description="Total geral de tarefas sob auditoria."
    )
    total_impedimentos: int = Field(
        ..., description="Total geral de impedimentos relatados."
    )
    setores: list[SectorDashboardResponse] = Field(
        ..., description="Detalhamento individual de cada setor ativo."
    )

    model_config = {"from_attributes": True}



