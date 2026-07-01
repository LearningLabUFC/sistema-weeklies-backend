"""
Sistema de Gestão LL — Backend
Entrypoint da aplicação FastAPI.
"""

from fastapi import FastAPI

from app.routers import auth, users

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

# ── Routers ──────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(users.router)


# ── Health check ─────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Health"],
    summary="Verifica se a API está no ar",
    response_description="Status da aplicação",
)
async def health_check():
    """Retorna o status atual da aplicação."""
    return {"status": "healthy"}
