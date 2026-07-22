"""
Sistema de Gestão LL — Backend
Entrypoint da aplicação FastAPI.
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import SessionLocal

from app.routers import auth, users

load_dotenv()
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(
    title="Sistema de Gestão LL",
    description=(
        "API RESTful avançada para o sistema de Gestão LL "
        "(UFC — Campus Russas). Gerenciamento completo de alunos, "
        "horas, weeklies, reuniões, setores e dashboard analítico."
    ),
    version="1.0.0",
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


# ── Routers ──────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(users.router)


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
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected", "error": str(e)},
        )
