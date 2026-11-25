"""fila de jobs (tabela jobs)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("max_tentativas", sa.Integer(), nullable=False),
        sa.Column("proxima_em", sa.DateTime(), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(), nullable=True),
        sa.Column("concluido_em", sa.DateTime(), nullable=True),
        sa.Column("erro", sa.String(300), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jobs_fila", "jobs", ["status", "proxima_em"])


def downgrade():
    op.drop_index("ix_jobs_fila", table_name="jobs")
    op.drop_table("jobs")
