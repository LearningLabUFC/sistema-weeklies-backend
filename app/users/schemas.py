from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.validators import _validar_nome_completo
from app.models.user import User


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
        description="ID referencial (UUID) do curso do usuario.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    status_id: UUID = Field(
        ...,
        description="ID referencial do status global.",
        examples=["1fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )
    global_role: UUID = Field(
        ...,
        description="ID referencial do papel global do usuário (usuario, coordenador, admin).",
        examples=["1fa85f64-5717-4562-b3fc-2c963f66afa1"],
    )


class UpdateProfileRequest(BaseModel):
    """Body para PUT /users/me."""

    nome_completo: str | None = Field(
        None,
        description="Novo nome completo do usuário.",
        examples=["João Pedro Silva"],
    )

    @field_validator("nome_completo")
    @classmethod
    def validar_nome_completo(cls, v: str | None) -> str | None:
        if v is not None:
            return _validar_nome_completo(v)
        return v

    email: EmailStr | None = Field(
        None,
        description="Novo endereço de e-mail do usuário.",
        examples=["joao.novo@exemplo.com"],
    )
    foto_perfil: str | None = Field(
        None,
        description="Novo caminho ou URL da foto de perfil.",
        examples=["avatar_joao_2026.png"],
    )


class UsuarioPerfilResponse(BaseModel):
    """Resposta para GET /users/me e PUT /users/me."""

    mensagem: str = Field(
        ...,
        examples=["Perfil obtido com sucesso."],
    )
    usuario: UsuarioCompleto


def build_usuario_completo(usuario: User) -> UsuarioCompleto:
    """Constrói o schema UsuarioCompleto a partir do model User."""
    return UsuarioCompleto(
        id=usuario.id,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        matricula=usuario.matricula,
        data_nascimento=usuario.data_nascimento,
        data_ingresso=usuario.data_ingresso,
        meta_horas_semanais=usuario.meta_horas_semanais,
        foto_perfil=usuario.foto_perfil,
        curso_id=usuario.curso_id,
        status_id=usuario.status_id,
        global_role=usuario.global_role,
    )
