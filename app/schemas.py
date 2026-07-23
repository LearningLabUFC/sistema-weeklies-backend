"""
Schemas Pydantic — gerados a partir do contrato OpenAPI (API First).

Cada modelo mapeia um componente/schema ou um body inline
definido no arquivo douglaslima-b57-Sistema-LL-1.0.0-unresolved.json.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ────────────────────────────────────────────
# Schemas reutilizáveis (components/schemas)
# ────────────────────────────────────────────

class ErroPadrao(BaseModel):
    """Estrutura padronizada para retorno de erros em requisições da API."""

    mensagem: str = Field(
        ...,
        description="Mensagem detalhando o motivo da falha.",
        examples=["Ocorreu um erro ao processar sua requisição."],
    )

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


# ────────────────────────────────────────────
# Auth — Request bodies
# ────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """Body para POST /auth/register."""

    nome_completo: str = Field(
        ...,
        description="Nome completo do usuário.",
        examples=["João Silva"],
    )
    email: EmailStr = Field(
        ...,
        examples=["joao@exemplo.com"],
    )
    senha: str = Field(
        ...,
        description="Senha do usuário.",
        examples=["SenhaForte123!"],
    )
    data_nascimento: date = Field(
        ...,
        examples=["2000-01-01"],
    )
    matricula: str = Field(
        ...,
        description="Matrícula da universidade.",
        examples=["512345"],
    )
    curso_id: UUID = Field(
        ...,
        description="UUID do curso acadêmico do aluno.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    metas_horas_semanais: int = Field(
        ...,
        description="Horas obrigatórias trabalhadas na semana",
        examples=[12]
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


# ────────────────────────────────────────────
# Auth — Response bodies
# ────────────────────────────────────────────

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


class MensagemResponse(BaseModel):
    """Resposta genérica contendo apenas uma mensagem textual."""

    mensagem: str = Field(
        ...,
        examples=["Operação realizada com sucesso."],
    )


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


# ────────────────────────────────────────────
# Auth — Rotas adicionais (M2)
# ────────────────────────────────────────────

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


class DeleteAccountRequest(BaseModel):
    """Body para DELETE /auth/account."""

    senha: str = Field(
        ...,
        description="Senha atual para confirmar a exclusão da conta.",
        examples=["SenhaForte123!"],
    )


# ────────────────────────────────────────────
# Users — Perfil do usuário (M2)
# ────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    """Body para PUT /users/me."""

    nome_completo: str | None = Field(
        None,
        description="Novo nome completo do usuário.",
        examples=["João Pedro Silva"],
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
