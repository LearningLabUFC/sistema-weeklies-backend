"""rename_aluno_to_usuario

Revision ID: dfe50706c0ed
Revises: 561d6626ca37
Create Date: 2026-09-25 19:18:47.414619

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dfe50706c0ed"
down_revision: str | None = "561d6626ca37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE cargos SET nome = 'usuario' WHERE nome = 'aluno'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE cargos SET nome = 'aluno' WHERE nome = 'usuario'")
