"""Constantes centralizadas do sistema."""

import uuid


class RoleName:
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USUARIO = "usuario"


class RoleID:
    SUPER_ADMIN = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa1")
    ADMIN = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa2")
    USUARIO = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa3")


class StatusName:
    PENDENTE = "pendente"
    ATIVO = "ativo"
    INATIVO = "inativo"


class StatusID:
    PENDENTE = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa1")
    ATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa2")
    INATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa3")


class TestID:
    """IDs de entidades criadas exclusivamente para testes."""

    CURSO_TESTE = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa4")
    SETOR_TESTE = uuid.UUID("4fa85f64-5717-4562-b3fc-2c963f66afa1")
