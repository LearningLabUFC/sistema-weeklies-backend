"""criar_tabela_cursos_e_popular_dados

Revision ID: 4ecade08b41e
Revises: d9a07eade5bf
Create Date: 2026-07-23 11:29:59.101977

"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4ecade08b41e'
down_revision: str | None = 'd9a07eade5bf'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    cursos_table = op.create_table(
        'cursos',
        sa.Column('id', sa.UUID(as_uuid=True),
                  primary_key=True, default=uuid.uuid4),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False,
                  server_default=sa.text('true'))
    )

    op.bulk_insert(
        cursos_table,
        [
            {
                'id': uuid.uuid4(),
                'nome': 'ciência da computação',
                'ativo': True
            },
            {
                'id': uuid.uuid4(),
                'nome': 'engenharia de software',
                'ativo': True
            },
            {
                'id': uuid.uuid4(),
                'nome': 'engenharia de produção',
                'ativo': True
            },
            {
                'id': uuid.uuid4(),
                'nome': 'engenharia mecânica',
                'ativo': False
            },
            {
                'id': uuid.uuid4(),
                'nome': 'engenharia civil',
                'ativo': False
            },
        ]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('cursos')
