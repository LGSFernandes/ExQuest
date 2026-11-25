"""métricas de velocidade de usuários reais (RUM)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "metricas_rum",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rota", sa.String(60), nullable=False),
        sa.Column("nome", sa.String(8), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("dispositivo", sa.String(8), nullable=False),
        sa.Column("conexao", sa.String(10), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_rum_rota", "metricas_rum", ["rota", "nome", "criado_em"])
    op.create_index("ix_rum_criado", "metricas_rum", ["criado_em"])


def downgrade():
    op.drop_index("ix_rum_criado", table_name="metricas_rum")
    op.drop_index("ix_rum_rota", table_name="metricas_rum")
    op.drop_table("metricas_rum")
