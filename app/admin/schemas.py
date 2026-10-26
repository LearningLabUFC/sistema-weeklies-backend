from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ChangeStatusRequest(BaseModel):
    """Body para PATCH /admin/users/{user_id}/status."""

    novo_status: str = Field(
        ...,
        description="Novo status do usuário. Valores aceitos: 'ativo', 'inativo'.",
        examples=["ativo"],
    )


class ChangeRoleRequest(BaseModel):
    """Body para PATCH /admin/users/{user_id}/role."""

    role_nome: str = Field(
        ...,
        description="Nome do novo cargo. Valores aceitos: 'super_admin', 'admin', 'usuario'.",
        examples=["admin"],
    )


class UsuarioListItem(BaseModel):
    """Item individual da listagem de usuários para admins (com nomes resolvidos)."""

    id: UUID = Field(
        ...,
        description="Identificador único (UUID) do usuário.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    nome_completo: str = Field(
        ...,
        description="Nome completo do usuário.",
        examples=["João Silva"],
    )
    email: EmailStr = Field(
        ...,
        examples=["joao@exemplo.com"],
    )
    matricula: str = Field(
        ...,
        description="Número de matrícula.",
        examples=["512345"],
    )
    data_ingresso: date = Field(
        ...,
        description="Data em que o usuário ingressou no projeto.",
        examples=["2024-05-20"],
    )
    foto_perfil: str = Field(
        ...,
        description="Caminho ou URL referente à foto de perfil.",
        examples=["avatar_padrao.png"],
    )
    curso_nome: str = Field(
        ...,
        description="Nome do curso do usuario (resolvido da relação).",
        examples=["Engenharia de Software"],
    )
    status_nome: str = Field(
        ...,
        description="Status atual do usuário (resolvido da relação).",
        examples=["ativo"],
    )
    role_nome: str = Field(
        ...,
        description="Cargo/papel do usuário (resolvido da relação).",
        examples=["usuario"],
    )


class UsuarioListResponse(BaseModel):
    """Resposta paginada para GET /admin/users."""

    usuarios: list[UsuarioListItem] = Field(
        ...,
        description="Lista de usuários na página atual.",
    )
    total: int = Field(
        ...,
        description="Número total de usuários que correspondem aos filtros.",
        examples=[42],
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
