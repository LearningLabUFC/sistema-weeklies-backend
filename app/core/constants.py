"""Constantes centralizadas do sistema."""

import uuid


class RoleID:
    SUPER_ADMIN = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa1")
    ADMIN = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa2")
    ALUNO = uuid.UUID("2fa85f64-5717-4562-b3fc-2c963f66afa3")


class StatusID:
    PENDENTE = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa1")
    ATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa2")
    INATIVO = uuid.UUID("1fa85f64-5717-4562-b3fc-2c963f66afa3")
