"""notificacoes.origem_id: quem gerou o aviso (anonimização na exclusão de conta)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notificacoes") as b:
        b.add_column(sa.Column("origem_id", sa.Integer(), nullable=True))
        b.create_index("ix_notificacoes_origem_id", ["origem_id"])


def downgrade():
    with op.batch_alter_table("notificacoes") as b:
        b.drop_index("ix_notificacoes_origem_id")
        b.drop_column("origem_id")
