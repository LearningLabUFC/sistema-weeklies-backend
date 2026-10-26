"""
Exception Handlers globais do FastAPI.

Captura exceções de domínio (AppException e subclasses) e as
traduz para respostas HTTP JSON padronizadas.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException


async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
    """Converte uma AppException em JSONResponse com status_code e detail."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
