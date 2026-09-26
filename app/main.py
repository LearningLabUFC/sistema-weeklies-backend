"""
Sistema de Gestão LL — Backend
Entrypoint da aplicação FastAPI.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api_router import api_router
from app.core.exception_handlers import handle_app_exception
from app.core.exceptions import AppException
from app.core.redis.connection import encerrar_redis, iniciar_redis
from app.database import SessionLocal

load_dotenv()
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


# ── Lifecycle (startup / shutdown) ───────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia recursos assíncronos: Redis."""
    await iniciar_redis()
    yield
    await encerrar_redis()


app = FastAPI(
    title="Sistema de Gestão LL",
    description=(
        "API RESTful avançada para o sistema de Gestão LL "
        "(UFC — Campus Russas). Gerenciamento completo de usuarios, "
        "horas, weeklies, reuniões, setores e dashboard analítico."
    ),
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "LearningLab",
        "email": "learninglab@ufc.br",
    },
    license_info={
        "name": "Todos os direitos reservados ao projeto interno do LearningLab UFC Campus Russas.",
        "url": "https://learninglab.com.br/",
    },
)

# ── Configuração de CORS ─────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception Handlers ───────────────────────────────────────

app.add_exception_handler(AppException, handle_app_exception)

# ── Routers ──────────────────────────────────────────────────

app.include_router(api_router)


# ── Health check ─────────────────────────────────────────────


@app.get(
    "/api/health",
    tags=["Health"],
    summary="Verifica se a API e o banco de dados estão no ar",
    response_description="Status da aplicação e conexão com o banco",
)
async def health_check():
    """Retorna o status atual da aplicação e valida a conexão com o banco de dados."""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
            },
        )
