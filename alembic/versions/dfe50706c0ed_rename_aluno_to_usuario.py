"""rename_aluno_to_usuario

Revision ID: dfe50706c0ed
Revises: 561d6626ca37
Create Date: 2026-09-25 19:18:47.414619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dfe50706c0ed'
down_revision: Union[str, None] = '561d6626ca37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE cargos SET nome = 'usuario' WHERE nome = 'aluno'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE cargos SET nome = 'aluno' WHERE nome = 'usuario'")
