"""
Configuração do SQLAlchemy — Engine, Session e Base.

Este módulo centraliza a conexão com o banco de dados PostgreSQL
e expõe a dependency `get_db` para injeção nas rotas FastAPI.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# ── Engine ───────────────────────────────────────────────────
# pool_pre_ping=True garante que conexões inativas sejam
# descartadas antes de serem reutilizadas pelo pool.

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# ── Session factory ──────────────────────────────────────────

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Base declarativa ─────────────────────────────────────────
# Todos os modelos ORM devem herdar desta classe.

Base = declarative_base()


# ── Dependency para injeção via FastAPI ──────────────────────

def get_db():
    """
    Gera uma sessão de banco de dados por requisição.

    Uso nos routers:
        @router.get("/exemplo")
        def exemplo(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
