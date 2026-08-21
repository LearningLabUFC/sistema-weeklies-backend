"""
Schemas Pydantic — gerados a partir do contrato OpenAPI (API First).

Cada modelo mapeia um componente/schema ou um body inline
definido no arquivo douglaslima-b57-Sistema-LL-1.0.0-unresolved.json.
"""

from __future__ import annotations

import re
from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Validação de senha forte ─────────────────────────────────

_SENHA_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)"
    r"(?=.*[!@#$%^&*()_+\-=\[\]{}|;:'\",.<>?/`~])"
    r".{8,}$"
)

_SENHA_MSG = (
    "A senha deve conter no mínimo 8 caracteres, incluindo "
    "letra maiúscula, letra minúscula, número e caractere especial."
)

_MATRICULA_REGEX = re.compile(r"^\d{6}$")
_MATRICULA_MSG = "A matrícula deve conter exatamente 6 dígitos numéricos."

_NOME_REGEX = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s'-]+$")
_NOME_MSG = "O nome completo deve conter apenas letras, acentos e espaços, e possuir ao menos nome e sobrenome."


def _validar_nome_completo(v: str) -> str:
    v = v.strip()
    if not v or not _NOME_REGEX.match(v) or len(v.split()) < 2:
        raise ValueError(_NOME_MSG)
    return v


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
        hoje = date.today()
        if v > hoje:
            raise ValueError("A data de nascimento não pode ser uma data futura.")
        if v.year < 1900:
            raise ValueError("O ano de nascimento deve ser a partir de 1900.")
        idade = hoje.year - v.year - ((hoje.month, hoje.day) < (v.month, v.day))
        if idade < 14:
            raise ValueError("O usuário deve ter no mínimo 14 anos de idade para se cadastrar.")
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

    @field_validator("nova_senha")
    @classmethod
    def validar_senha_forte(cls, v: str) -> str:
        if not _SENHA_REGEX.match(v):
            raise ValueError(_SENHA_MSG)
        return v


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


# ────────────────────────────────────────────
# Admin — Gerenciamento de usuários
# ────────────────────────────────────────────

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
        description="Nome do novo cargo. Valores aceitos: 'super_admin', 'admin', 'aluno'.",
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
        description="Nome do curso do aluno (resolvido da relação).",
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
        examples=["aluno"],
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
