"""Alinhar o ID do histórico do scheduler ao modelo UUID.

Revision ID: b7f3a920d641
Revises: 9176f5980bb7
"""

import sqlalchemy as sa

from alembic import op

revision = "b7f3a920d641"
down_revision = "9176f5980bb7"
branch_labels = None
depends_on = None

TABLE = "weekly_scheduler_execucoes"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # Algumas instalações aplicaram a primeira versão de 9176 antes desta tabela existir.
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("tipo", sa.String(50), nullable=False),
            sa.Column("semana_referencia", sa.Date(), nullable=False),
            sa.Column(
                "executado_em",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "tipo", "semana_referencia", name="uq_scheduler_tipo_semana"
            ),
        )
    else:
        id_column = next(c for c in inspector.get_columns(TABLE) if c["name"] == "id")
        if isinstance(id_column["type"], sa.Integer):
            op.alter_column(TABLE, "id", server_default=None)
            op.execute(f"DROP SEQUENCE IF EXISTS {TABLE}_id_seq")
            # IDs internos sem referências externas. Preserva todas as execuções existentes.
            op.alter_column(
                TABLE,
                "id",
                existing_type=sa.Integer(),
                type_=sa.Uuid(),
                postgresql_using="md5('weekly_scheduler_execucoes:' || id::text)::uuid",
            )
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    for column in ("tipo", "semana_referencia"):
        name = f"ix_{TABLE}_{column}"
        if name not in indexes:
            op.create_index(name, TABLE, [column])


def downgrade() -> None:
    # Reatribui IDs internos inteiros, mantendo tipo, semana e data de cada execução.
    op.add_column(
        TABLE, sa.Column("integer_id", sa.Integer(), sa.Identity(), nullable=False)
    )
    op.alter_column(
        TABLE,
        "id",
        existing_type=sa.Uuid(),
        type_=sa.Integer(),
        postgresql_using="integer_id",
    )
    op.drop_column(TABLE, "integer_id")
    op.execute(f"CREATE SEQUENCE {TABLE}_id_seq OWNED BY {TABLE}.id")
    op.alter_column(
        TABLE, "id", server_default=sa.text(f"nextval('{TABLE}_id_seq'::regclass)")
    )
    op.execute(
        f"SELECT setval(pg_get_serial_sequence('{TABLE}', 'id'), "
        f"COALESCE(MAX(id), 0) + 1, false) FROM {TABLE}"
    )
