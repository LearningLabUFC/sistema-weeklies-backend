from uuid import UUID

from pydantic import BaseModel, Field


class CursoResumo(BaseModel):
    """Resumo público de um curso retornado pela API de domínio."""

    id: UUID = Field(
        ...,
        description="Identificador único (UUID) do curso.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    nome: str = Field(
        ...,
        description="Nome do curso.",
        examples=["Engenharia de Software"],
    )
    ativo: bool = Field(
        ...,
        description="Indica se o curso está ativo no sistema.",
        examples=[True],
    )
