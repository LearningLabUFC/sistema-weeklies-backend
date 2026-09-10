"""Schemas Pydantic globais (usados por múltiplos módulos)."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


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


class UsuarioCompleto(BaseModel):
    """
    Objeto que mapeia todos os dados públicos da tabela 'usuarios',
    omitindo dados sensíveis como o hash da senha.
    """

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
        description="Número de matrícula, operando como chave única.",
        examples=["512345"],
    )
    data_nascimento: date = Field(
        ...,
        examples=["2000-01-01"],
    )
    data_ingresso: date = Field(
        ...,
        description="Data em que o usuário ingressou no projeto.",
        examples=["2024-05-20"],
    )
    meta_horas_semanais: int = Field(
        ...,
        description="Meta de horas semanais a serem cumpridas pelo membro.",
        examples=[12],
    )
    foto_perfil: str = Field(
        ...,
        description="Caminho ou URL referente à foto de perfil do usuário.",
        examples=["avatar_padrao.png"],
    )
    curso_id: UUID = Field(
        ...,
        description="ID referencial (UUID) do curso do aluno.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    status_id: UUID = Field(
        ...,
        description="ID referencial do status global.",
        examples=["1fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    global_role: UUID = Field(
        ...,
        description="ID referencial do papel global do usuário (aluno, coordenador, admin).",
        examples=["1fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
