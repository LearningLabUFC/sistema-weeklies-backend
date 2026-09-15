"""Schemas Pydantic para o módulo de Setores."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ── Requests ─────────────────────────────────────────────────


class CreateSectorRequest(BaseModel):
    """Body para POST /sectors."""

    nome: str = Field(
        ...,
        max_length=100,
        description="Nome do setor. Deve ser único.",
        examples=["Desenvolvimento"],
    )
    descricao: str | None = Field(
        None,
        description="Descrição do setor.",
        examples=["Setor responsável pelo desenvolvimento de software."],
    )


class UpdateSectorRequest(BaseModel):
    """Body para PATCH /sectors/{sector_id}."""

    nome: str | None = Field(
        None,
        max_length=100,
        description="Novo nome do setor.",
        examples=["Desenvolvimento Web"],
    )
    descricao: str | None = Field(
        None,
        description="Nova descrição do setor.",
        examples=["Setor focado em desenvolvimento web e mobile."],
    )
    ativo: bool | None = Field(
        None,
        description="Status de ativação do setor.",
        examples=[True],
    )


class AddMemberRequest(BaseModel):
    """Body para POST /sectors/{sector_id}/members."""

    usuario_id: UUID = Field(
        ...,
        description="UUID do usuário a ser adicionado ao setor.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    papel: str = Field(
        "membro",
        description="Papel do usuário no setor. Valores aceitos: 'lider', 'membro'.",
        examples=["membro"],
    )


class ChangeMemberRoleRequest(BaseModel):
    """Body para PATCH /sectors/{sector_id}/members/{user_id}/role."""

    papel: str = Field(
        ...,
        description="Novo papel do usuário no setor. Valores aceitos: 'lider', 'membro'.",
        examples=["lider"],
    )


# ── Responses ────────────────────────────────────────────────


class SectorMemberItem(BaseModel):
    """Representa um membro dentro de um setor."""

    id: UUID = Field(
        ...,
        description="UUID do usuário.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    nome_completo: str = Field(
        ...,
        description="Nome completo do usuário.",
        examples=["João Silva"],
    )
    email: str = Field(
        ...,
        examples=["joao@exemplo.com"],
    )
    papel: str = Field(
        ...,
        description="Papel do usuário neste setor ('lider' ou 'membro').",
        examples=["membro"],
    )


class SectorListItem(BaseModel):
    """Item da listagem de setores."""

    id: UUID = Field(
        ...,
        description="UUID do setor.",
        examples=["4fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    nome: str = Field(
        ...,
        description="Nome do setor.",
        examples=["Desenvolvimento"],
    )
    descricao: str | None = Field(
        None,
        description="Descrição do setor.",
        examples=["Setor responsável pelo desenvolvimento de software."],
    )
    ativo: bool = Field(
        ...,
        description="Se o setor está ativo.",
        examples=[True],
    )
    criado_em: datetime = Field(
        ...,
        description="Data e hora de criação do setor.",
    )
    qtd_membros: int = Field(
        ...,
        description="Quantidade de membros (papel='membro') no setor.",
        examples=[5],
    )
    qtd_lideres: int = Field(
        ...,
        description="Quantidade de líderes (papel='lider') no setor.",
        examples=[1],
    )


class SectorDetail(BaseModel):
    """Detalhamento completo de um setor, incluindo seus membros."""

    id: UUID = Field(
        ...,
        description="UUID do setor.",
    )
    nome: str = Field(
        ...,
        description="Nome do setor.",
    )
    descricao: str | None = Field(
        None,
        description="Descrição do setor.",
    )
    ativo: bool = Field(
        ...,
        description="Se o setor está ativo.",
    )
    criado_em: datetime = Field(
        ...,
        description="Data e hora de criação do setor.",
    )
    membros: list[SectorMemberItem] = Field(
        ...,
        description="Lista de usuários associados a este setor.",
    )


class SectorListResponse(BaseModel):
    """Resposta paginada para GET /sectors."""

    setores: list[SectorListItem] = Field(
        ...,
        description="Lista de setores na página atual.",
    )
    total: int = Field(
        ...,
        description="Número total de setores.",
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
