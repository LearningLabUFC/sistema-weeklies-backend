"""
Alembic env.py — Configuração de migrations.

Conecta o Alembic ao banco de dados usando as configurações
de app.config e detecta os modelos ORM via app.models.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Importar todos os modelos para que Base.metadata conheça as tabelas.
import app.models  # noqa: F401
from alembic import context
from app.config import settings
from app.database import Base

# ── Alembic Config object ───────────────────────────────────

config = context.config

# Setar a URL do banco de dados a partir do nosso Settings,
# substituindo qualquer valor do alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configurar loggers a partir do alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata dos modelos ORM — o Alembic usa isso para
# comparar o estado do banco com o estado do código.
target_metadata = Base.metadata


# ── Modo offline (gera SQL sem conectar ao banco) ────────────

def run_migrations_offline() -> None:
    """Executa migrations em modo 'offline' (gera SQL sem conectar ao banco)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Modo online (conecta ao banco e aplica migrations) ───────

def run_migrations_online() -> None:
    """Executa migrations em modo 'online' (conecta ao banco e aplica as alterações)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
