from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.schemas import UsuarioCompleto
from app.core.validators import _validar_nome_completo


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
