"""Schemas para o módulo de Autenticação."""

from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.schemas import UsuarioCompleto
from app.core.validators import (
    _MATRICULA_MSG,
    _MATRICULA_REGEX,
    _SENHA_MSG,
    _SENHA_REGEX,
    _validar_nome_completo,
)


class RegisterRequest(BaseModel):
    """Body para POST /auth/register."""

    nome_completo: str = Field(
        ...,
        description="Nome completo do usuário (ao menos nome e sobrenome).",
        examples=["João Silva"],
    )

    @field_validator("nome_completo")
    @classmethod
    def validar_nome_completo(cls, v: str) -> str:
        return _validar_nome_completo(v)

    email: EmailStr = Field(
        ...,
        examples=["joao@exemplo.com"],
    )
    senha: str = Field(
        ...,
        description="Senha do usuário.",
        examples=["SenhaForte123!"],
    )

    @field_validator("senha")
    @classmethod
    def validar_senha_forte(cls, v: str) -> str:
        if not _SENHA_REGEX.match(v):
            raise ValueError(_SENHA_MSG)
        return v

    data_nascimento: date = Field(
        ...,
        description="Data de nascimento do usuário.",
        examples=["2000-01-01"],
    )

    @field_validator("data_nascimento")
    @classmethod
    def validar_data_nascimento(cls, v: date) -> date:
        hoje = datetime.now(tz=timezone.utc).date()
        if v > hoje:
            raise ValueError("A data de nascimento não pode ser uma data futura.")
        if v.year < 1900:
            raise ValueError("O ano de nascimento deve ser a partir de 1900.")
        idade = hoje.year - v.year - ((hoje.month, hoje.day) < (v.month, v.day))
        if idade < 14:
            raise ValueError(
                "O usuário deve ter no mínimo 14 anos de idade para se cadastrar."
            )
        if idade > 120:
            raise ValueError("Data de nascimento inválida (idade máxima excedida).")
        return v

    matricula: str = Field(
        ...,
        description="Matrícula da universidade (exatamente 6 dígitos numéricos).",
        examples=["512345"],
    )

    @field_validator("matricula")
    @classmethod
    def validar_matricula(cls, v: str) -> str:
        v = v.strip()
        if not _MATRICULA_REGEX.match(v):
            raise ValueError(_MATRICULA_MSG)
        return v

    curso_id: UUID = Field(
        ...,
        description="UUID do curso acadêmico do aluno.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    meta_horas_semanais: int = Field(
        ..., description="Horas obrigatórias trabalhadas na semana", examples=[12]
    )


class LoginRequest(BaseModel):
    """Body para POST /auth/login."""

    email: EmailStr = Field(
        ...,
        examples=["joao@exemplo.com"],
    )
    senha: str = Field(
        ...,
        description="Senha do usuário.",
        examples=["SenhaForte123!"],
    )


class ForgotPasswordRequest(BaseModel):
    """Body para POST /auth/forgot-password."""

    email: EmailStr = Field(
        ...,
        examples=["joao@exemplo.com"],
    )


class VerifyCodeRequest(BaseModel):
    """Body para POST /auth/verify-code."""

    email: EmailStr = Field(
        ...,
        examples=["joao@exemplo.com"],
    )
    codigo: str = Field(
        ...,
        description="Código numérico de 6 dígitos enviado por e-mail.",
        examples=["482910"],
    )


class ResetPasswordRequest(BaseModel):
    """Body para POST /auth/reset-password."""

    token_redefinicao: str = Field(
        ...,
        description="Token temporário gerado na etapa de verificação de código.",
        examples=["abc123xyz890tokenTemporario"],
    )
    nova_senha: str = Field(
        ...,
        description="Nova senha que substituirá a anterior.",
        examples=["NovaSenhaSegura2026!"],
    )

    @field_validator("nova_senha")
    @classmethod
    def validar_senha_forte(cls, v: str) -> str:
        if not _SENHA_REGEX.match(v):
            raise ValueError(_SENHA_MSG)
        return v


class AuthTokenResponse(BaseModel):
    """
    Resposta de sucesso para register (201) e login (200).
    Contém tokens JWT e os dados completos do usuário.
    """

    mensagem: str = Field(
        ...,
        examples=["Login realizado com sucesso."],
    )
    token_acesso: str = Field(
        ...,
        description="Token JWT contendo o nível de acesso (role) no payload.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...signature"],
    )
    tipo_token: str = Field(
        ...,
        examples=["bearer"],
    )
    token_atualizacao: str = Field(
        ...,
        description="Refresh token para renovação do acesso.",
        examples=["def50200543e332..."],
    )
    usuario: UsuarioCompleto


class VerifyCodeResponse(BaseModel):
    """Resposta de sucesso para POST /auth/verify-code."""

    mensagem: str = Field(
        ...,
        examples=["Código validado com sucesso."],
    )
    token_redefinicao: str = Field(
        ...,
        description="Token temporário para redefinição de senha.",
        examples=["abc123xyz890tokenTemporario"],
    )


class LogoutRequest(BaseModel):
    """Body opcional para POST /auth/logout."""

    token_atualizacao: str | None = Field(
        None,
        description="Refresh token opcional para revogação no momento do logout.",
        examples=["def50200543e332..."],
    )


class RefreshTokenRequest(BaseModel):
    """Body para POST /auth/refresh."""

    token_atualizacao: str = Field(
        ...,
        description="Refresh token obtido no login ou registro.",
        examples=["def50200543e332..."],
    )


class RefreshTokenResponse(BaseModel):
    """Resposta de sucesso para POST /auth/refresh."""

    mensagem: str = Field(
        ...,
        examples=["Token renovado com sucesso."],
    )
    token_acesso: str = Field(
        ...,
        description="Novo token JWT de acesso.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...novoToken"],
    )
    tipo_token: str = Field(
        ...,
        examples=["bearer"],
    )
    token_atualizacao: str = Field(
        ...,
        description="Novo refresh token (rotação de tokens).",
        examples=["ghi78900novoRefreshToken..."],
    )


class ChangePasswordRequest(BaseModel):
    """Body para PUT /auth/change-password."""

    senha_atual: str = Field(
        ...,
        description="Senha atual do usuário para confirmação.",
        examples=["SenhaForte123!"],
    )
    nova_senha: str = Field(
        ...,
        description="Nova senha que substituirá a atual.",
        examples=["NovaSenhaSegura2026!"],
    )

    @field_validator("nova_senha")
    @classmethod
    def validar_senha_forte(cls, v: str) -> str:
        if not _SENHA_REGEX.match(v):
            raise ValueError(_SENHA_MSG)
        return v


class DeleteAccountRequest(BaseModel):
    """Body para DELETE /auth/account."""

    senha: str = Field(
        ...,
        description="Senha atual para confirmar a exclusão da conta.",
        examples=["SenhaForte123!"],
    )
