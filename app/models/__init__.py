"""
Pacote de modelos ORM.

Importa todos os modelos aqui para que o Alembic consiga
detectar as tabelas via Base.metadata ao gerar migrations.
"""

from app.models.user import User  # noqa: F401
