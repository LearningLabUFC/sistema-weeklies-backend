"""Schemas Pydantic globais (usados por múltiplos módulos)."""

from pydantic import BaseModel, Field


class ErroPadrao(BaseModel):
    """Estrutura padronizada para retorno de erros em requisições da API."""

    mensagem: str = Field(
        ...,
        description="Mensagem detalhando o motivo da falha.",
        examples=["Ocorreu um erro ao processar sua requisição."],
    )


class MensagemResponse(BaseModel):
    """Resposta genérica de sucesso que retorna apenas uma mensagem."""

    mensagem: str = Field(..., description="Mensagem de sucesso.")
