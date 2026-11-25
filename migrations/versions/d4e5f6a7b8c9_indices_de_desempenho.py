"""índices para as consultas mais comuns (ranking, competições, assinaturas, pagamentos, chat, recuperação de senha)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

INDICES = [
    ("ix_usuarios_ranking", "usuarios", ["is_banido", "xp"]),
    ("ix_torneios_status_fim", "torneios", ["status", "fim"]),
    ("ix_torneios_inicio", "torneios", ["inicio"]),
    ("ix_assinaturas_expira", "assinaturas", ["status", "expira"]),
    ("ix_pagamentos_status", "pagamentos", ["status", "criado_em"]),
    ("ix_mensagens_remetente", "mensagens", ["remetente_id", "enviado_em"]),
    ("ix_tokens_usuario_usado", "tokens_recuperacao", ["usuario_id", "usado"]),
]


def upgrade():
    for nome, tabela, cols in INDICES:
        op.create_index(nome, tabela, cols)


def downgrade():
    for nome, tabela, _ in reversed(INDICES):
        op.drop_index(nome, table_name=tabela)
