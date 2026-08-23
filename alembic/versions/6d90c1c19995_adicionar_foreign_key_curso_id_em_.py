"""adicionar_foreign_key_curso_id_em_usuarios

Revision ID: 6d90c1c19995
Revises: 4ecade08b41e
Create Date: 2026-07-23 11:36:08.242400

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6d90c1c19995'
down_revision: str | None = '4ecade08b41e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        'fk_usuarios_curso_id_cursos',
        'usuarios',
        'cursos',
        ['curso_id'],
        ['id'],
        ondelete='RESTRICT'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_usuarios_curso_id_cursos',
                       'usuarios', type_='foreignkey')
