"""delta v2: reengenharia (carteira/ledger, pagamentos, estudo, social, índices)

Somente aditiva: cria tabelas/colunas/índices e faz backfills idempotentes. Nenhum dado é removido ou reescrito,
exceto o preenchimento de colunas novas. Índices únicos novos só são criados se os dados atuais os respeitarem;
caso contrário a migration ABORTA (sem alterar nada) e lista os registros duplicados para correção manual.


Revision ID: a1b2c3d4e5f6
Revises: 62e588f5787b
Create Date: 2026-11-11

"""
from alembic import op
import re
import unicodedata
from datetime import datetime, timezone

import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '62e588f5787b'
branch_labels = None
depends_on = None


def upgrade():
    _abortar_se_houver_duplicados()

    op.create_table('eventos_webhook',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('evento_id', sa.String(length=200), nullable=False),
    sa.Column('tipo', sa.String(length=80), nullable=True),
    sa.Column('resultado', sa.String(length=40), nullable=True),
    sa.Column('recebido_em', sa.DateTime(), nullable=False),
    sa.Column('processado_em', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('eventos_webhook', schema=None) as batch_op:
        batch_op.create_index('uq_evento_webhook', ['provider', 'evento_id'], unique=True)

    op.create_table('bloqueios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bloqueador_id', sa.Integer(), nullable=False),
    sa.Column('bloqueado_id', sa.Integer(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['bloqueado_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['bloqueador_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bloqueios', schema=None) as batch_op:
        batch_op.create_index('uq_bloqueio_par', ['bloqueador_id', 'bloqueado_id'], unique=True)

    op.create_table('carteira_lancamentos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('categoria', sa.String(length=30), nullable=False),
    sa.Column('valor', sa.Integer(), nullable=False),
    sa.Column('saldo_apos', sa.Integer(), nullable=False),
    sa.Column('referencia_tipo', sa.String(length=30), nullable=True),
    sa.Column('referencia_id', sa.String(length=64), nullable=True),
    sa.Column('chave_idempotencia', sa.String(length=120), nullable=False),
    sa.Column('descricao', sa.String(length=200), nullable=True),
    sa.Column('origem', sa.String(length=20), nullable=True),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['criado_por_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('carteira_lancamentos', schema=None) as batch_op:
        batch_op.create_index('ix_carteira_usuario_data', ['usuario_id', 'criado_em'], unique=False)
        batch_op.create_index('uq_carteira_chave', ['chave_idempotencia'], unique=True)

    op.create_table('colecoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=80), nullable=False),
    sa.Column('eh_favoritos', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('colecoes', schema=None) as batch_op:
        batch_op.create_index('uq_colecao_nome', ['usuario_id', 'nome'], unique=True)

    op.create_table('denuncias',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('autor_id', sa.Integer(), nullable=False),
    sa.Column('alvo_tipo', sa.String(length=20), nullable=False),
    sa.Column('alvo_id', sa.Integer(), nullable=False),
    sa.Column('motivo', sa.String(length=40), nullable=False),
    sa.Column('detalhe', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('resolvida_por_id', sa.Integer(), nullable=True),
    sa.Column('resolvida_em', sa.DateTime(), nullable=True),
    sa.Column('nota_admin', sa.String(length=500), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['autor_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['resolvida_por_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('denuncias', schema=None) as batch_op:
        batch_op.create_index('ix_denuncias_status', ['status', 'criado_em'], unique=False)

    op.create_table('missoes_progresso',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('missao_slug', sa.String(length=60), nullable=False),
    sa.Column('periodo_chave', sa.String(length=20), nullable=False),
    sa.Column('progresso', sa.Integer(), nullable=False),
    sa.Column('meta', sa.Integer(), nullable=False),
    sa.Column('concluida_em', sa.DateTime(), nullable=True),
    sa.Column('resgatada_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('missoes_progresso', schema=None) as batch_op:
        batch_op.create_index('uq_missao_periodo', ['usuario_id', 'missao_slug', 'periodo_chave'], unique=True)

    op.create_table('notificacoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('titulo', sa.String(length=120), nullable=False),
    sa.Column('corpo', sa.String(length=300), nullable=True),
    sa.Column('url', sa.String(length=200), nullable=True),
    sa.Column('lida', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notificacoes', schema=None) as batch_op:
        batch_op.create_index('ix_notif_usuario', ['usuario_id', 'lida', 'criado_em'], unique=False)

    op.create_table('pagamentos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('produto_ref', sa.String(length=60), nullable=False),
    sa.Column('descricao', sa.String(length=200), nullable=True),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_ref', sa.String(length=200), nullable=True),
    sa.Column('provider_payment_id', sa.String(length=200), nullable=True),
    sa.Column('valor_centavos', sa.Integer(), nullable=False),
    sa.Column('moeda', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('moedas_total', sa.Integer(), nullable=True),
    sa.Column('bonus_primeira', sa.Boolean(), nullable=True),
    sa.Column('plano', sa.String(length=20), nullable=True),
    sa.Column('ciclo', sa.String(length=10), nullable=True),
    sa.Column('chave_idempotencia', sa.String(length=120), nullable=False),
    sa.Column('observacao', sa.String(length=300), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), nullable=True),
    sa.Column('aprovado_em', sa.DateTime(), nullable=True),
    sa.Column('reembolsado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pagamentos', schema=None) as batch_op:
        batch_op.create_index('ix_pagamentos_provider_pay', ['provider', 'provider_payment_id'], unique=False)
        batch_op.create_index('ix_pagamentos_provider_ref', ['provider', 'provider_ref'], unique=False)
        batch_op.create_index('ix_pagamentos_usuario', ['usuario_id', 'criado_em'], unique=False)
        batch_op.create_index('uq_pagamentos_chave', ['chave_idempotencia'], unique=True)

    op.create_table('simulado_sessoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('token', sa.String(length=40), nullable=False),
    sa.Column('questoes_json', sa.Text(), nullable=False),
    sa.Column('filtros_json', sa.Text(), nullable=True),
    sa.Column('iniciado_em', sa.DateTime(), nullable=False),
    sa.Column('limite_segundos', sa.Integer(), nullable=False),
    sa.Column('finalizado_em', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('acertos', sa.Integer(), nullable=True),
    sa.Column('total', sa.Integer(), nullable=True),
    sa.Column('xp_total', sa.Integer(), nullable=True),
    sa.Column('moedas_total', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('simulado_sessoes', schema=None) as batch_op:
        batch_op.create_index('ix_simulado_usuario', ['usuario_id', 'iniciado_em'], unique=False)
        batch_op.create_index('uq_simulado_token', ['token'], unique=True)

    op.create_table('xp_eventos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('valor', sa.Integer(), nullable=False),
    sa.Column('origem', sa.String(length=30), nullable=False),
    sa.Column('referencia', sa.String(length=64), nullable=True),
    sa.Column('chave', sa.String(length=120), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('xp_eventos', schema=None) as batch_op:
        batch_op.create_index('ix_xp_eventos_data', ['criado_em', 'usuario_id'], unique=False)
        batch_op.create_index('ix_xp_eventos_usuario', ['usuario_id'], unique=False)
        batch_op.create_index('uq_xp_eventos_chave', ['chave'], unique=True)

    op.create_table('colecao_itens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('colecao_id', sa.Integer(), nullable=False),
    sa.Column('questao_id', sa.Integer(), nullable=False),
    sa.Column('adicionado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['colecao_id'], ['colecoes.id'], ),
    sa.ForeignKeyConstraint(['questao_id'], ['questoes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('colecao_itens', schema=None) as batch_op:
        batch_op.create_index('uq_colecao_item', ['colecao_id', 'questao_id'], unique=True)

    op.create_table('revisoes_questao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('questao_id', sa.Integer(), nullable=False),
    sa.Column('facilidade', sa.Float(), nullable=False),
    sa.Column('intervalo_dias', sa.Integer(), nullable=False),
    sa.Column('repeticoes', sa.Integer(), nullable=False),
    sa.Column('lapsos', sa.Integer(), nullable=False),
    sa.Column('proxima_em', sa.DateTime(), nullable=False),
    sa.Column('ultima_em', sa.DateTime(), nullable=True),
    sa.Column('origem', sa.String(length=20), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['questao_id'], ['questoes.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('revisoes_questao', schema=None) as batch_op:
        batch_op.create_index('ix_revisao_devida', ['usuario_id', 'ativo', 'proxima_em'], unique=False)
        batch_op.create_index('uq_revisao_usuario_questao', ['usuario_id', 'questao_id'], unique=True)

    op.create_table('torneio_questoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('torneio_id', sa.Integer(), nullable=False),
    sa.Column('questao_id', sa.Integer(), nullable=False),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['questao_id'], ['questoes.id'], ),
    sa.ForeignKeyConstraint(['torneio_id'], ['torneios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('torneio_questoes', schema=None) as batch_op:
        batch_op.create_index('uq_torneio_questao', ['torneio_id', 'questao_id'], unique=True)

    with op.batch_alter_table('alternativas', schema=None) as batch_op:
        batch_op.create_index('ix_alternativas_questao', ['questao_id'], unique=False)

    with op.batch_alter_table('amizades', schema=None) as batch_op:
        batch_op.create_index('ix_amizade_dest', ['destinatario_id', 'status'], unique=False)
        batch_op.create_index('uq_amizade_par', ['solicitante_id', 'destinatario_id'], unique=True)

    with op.batch_alter_table('assinaturas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('provider_assinatura_id', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('cancelar_ao_fim', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('atualizado_em', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_assinaturas_usuario', ['usuario_id', 'status'], unique=False)

    with op.batch_alter_table('grupo_membros', schema=None) as batch_op:
        batch_op.create_index('ix_grupo_membro_usuario', ['usuario_id'], unique=False)
        batch_op.create_index('uq_grupo_membro', ['grupo_id', 'usuario_id'], unique=True)

    with op.batch_alter_table('grupos_chat', schema=None) as batch_op:
        batch_op.add_column(sa.Column('icone_chave', sa.String(length=40), nullable=True))

    with op.batch_alter_table('inventario', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expira_em', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('origem', sa.String(length=30), nullable=True))
        batch_op.create_index('uq_inventario_usuario_item', ['usuario_id', 'item_id'], unique=True)

    with op.batch_alter_table('itens_loja', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slug', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('duracao_dias', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('config_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('ordem', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('disponivel_ate', sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint('uq_itens_loja_slug', ['slug'])

    with op.batch_alter_table('log_auditoria', schema=None) as batch_op:
        batch_op.create_index('ix_log_acao', ['acao', 'criado_em'], unique=False)
        batch_op.create_index('ix_log_criado', ['criado_em'], unique=False)

    with op.batch_alter_table('materias', schema=None) as batch_op:
        batch_op.add_column(sa.Column('icone_chave', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table('mensagens', schema=None) as batch_op:
        batch_op.create_index('ix_mensagens_grupo', ['grupo_id', 'id'], unique=False)

    with op.batch_alter_table('ofertas_trial', schema=None) as batch_op:
        batch_op.create_index('uq_trial_usuario', ['usuario_id'], unique=True)

    with op.batch_alter_table('questoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.create_index('ix_questoes_materia_dif', ['materia_id', 'dificuldade'], unique=False)

    with op.batch_alter_table('questoes_respondidas_sessao', schema=None) as batch_op:
        batch_op.create_index('ix_qrs_usuario_sessao', ['usuario_id', 'sessao_id'], unique=False)

    with op.batch_alter_table('recompensas_nivel', schema=None) as batch_op:
        batch_op.create_index('uq_recompensa_nivel', ['usuario_id', 'nivel'], unique=True)

    with op.batch_alter_table('respostas_usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('simulado_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('tempo_ms', sa.Integer(), nullable=True))
        batch_op.create_index('ix_respostas_questao', ['questao_id'], unique=False)
        batch_op.create_index('ix_respostas_usuario_data', ['usuario_id', 'data_resposta'], unique=False)
        batch_op.create_index('ix_respostas_usuario_questao', ['usuario_id', 'questao_id'], unique=False)

    with op.batch_alter_table('streaks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('escudos', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index('uq_streaks_usuario', ['usuario_id'], unique=True)

    with op.batch_alter_table('torneio_participantes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('iniciou_em', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('terminou_em', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_torneio_part_usuario', ['usuario_id'], unique=False)
        batch_op.create_index('uq_torneio_participante', ['torneio_id', 'usuario_id'], unique=True)

    with op.batch_alter_table('torneio_respostas', schema=None) as batch_op:
        batch_op.create_index('uq_torneio_resposta', ['participante_id', 'questao_id'], unique=True)

    with op.batch_alter_table('torneios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('finalizado_em', sa.DateTime(), nullable=True))

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fundo_ativo', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('titulo_ativo', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('nome_fx_ativo', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('tema_ativo', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('perfil_publico', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('questoes_bonus', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))

    _backfill()


# Índices únicos novos: (tabela, colunas). Verificados ANTES de qualquer alteração.
_UNICOS = [
    ("amizades", ("solicitante_id", "destinatario_id")),
    ("grupo_membros", ("grupo_id", "usuario_id")),
    ("inventario", ("usuario_id", "item_id")),
    ("ofertas_trial", ("usuario_id",)),
    ("recompensas_nivel", ("usuario_id", "nivel")),
    ("streaks", ("usuario_id",)),
    ("torneio_participantes", ("torneio_id", "usuario_id")),
    ("torneio_respostas", ("participante_id", "questao_id")),
]


def _abortar_se_houver_duplicados():
    bind = op.get_bind()
    problemas = []
    for tabela, cols in _UNICOS:
        lista = ", ".join(cols)
        rows = bind.execute(sa.text(
            f"SELECT {lista}, COUNT(*) AS n FROM {tabela} GROUP BY {lista} HAVING COUNT(*) > 1")).fetchall()
        if rows:
            problemas.append(f"{tabela}({lista}): {[tuple(r) for r in rows[:10]]}")
    if problemas:
        raise RuntimeError(
            "Migration abortada sem alterar o banco: há registros duplicados que impediriam índices únicos. "
            "Corrija manualmente (mantendo o registro de menor id) e rode de novo:\n  " + "\n  ".join(problemas))


def _slug(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:80]


# palavras do nome da matéria -> ícone; depois emoji legado; por fim o padrão
_ICONE_POR_NOME = [("hist", "landmark"), ("fis", "atom"), ("mat", "calculator"), ("quim", "flask-conical"),
                   ("bio", "dna"), ("port", "pen-line"), ("geo", "globe"), ("ingl", "languages"),
                   ("filos", "brain"), ("soci", "users"), ("progr", "code")]
_ICONE_POR_EMOJI = {"📚": "book-open", "📖": "book-open", "🧮": "calculator", "🧪": "flask-conical",
                    "🔬": "flask-conical", "🌍": "globe", "🌎": "globe", "🏛": "landmark", "📜": "scroll",
                    "🔧": "wrench", "⚛": "atom", "🧬": "dna", "💻": "code", "📐": "ruler", "🎨": "palette",
                    "🎵": "music", "✏": "pencil", "🗺": "map"}


def _icone_materia(nome, emoji):
    n = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    for trecho, chave in _ICONE_POR_NOME:
        if trecho in n:
            return chave
    return _ICONE_POR_EMOJI.get((emoji or "").replace("\ufe0f", ""), "book-open")


def _backfill():
    bind = op.get_bind()
    agora = datetime.now(timezone.utc).replace(tzinfo=None)

    # slug estável dos itens da loja (usa css_class quando existe; evita colisão com sufixo do id)
    itens = bind.execute(sa.text("SELECT id, nome, css_class FROM itens_loja WHERE slug IS NULL ORDER BY id")).fetchall()
    usados = {r[0] for r in bind.execute(sa.text("SELECT slug FROM itens_loja WHERE slug IS NOT NULL"))}
    for i, (item_id, nome, css) in enumerate(itens):
        base = _slug(css or nome) or f"item-{item_id}"
        slug = base if base not in usados else f"{base}-{item_id}"
        usados.add(slug)
        bind.execute(sa.text("UPDATE itens_loja SET slug = :s, ordem = COALESCE(ordem, :o) WHERE id = :i"),
                     {"s": slug, "o": (i + 1) * 10, "i": item_id})

    # ícones vetoriais no lugar dos emojis (a coluna `icone` legada é preservada)
    for mid, nome, emoji in bind.execute(sa.text("SELECT id, nome, icone FROM materias WHERE icone_chave IS NULL")).fetchall():
        bind.execute(sa.text("UPDATE materias SET icone_chave = :k WHERE id = :i"),
                     {"k": _icone_materia(nome, emoji), "i": mid})
    bind.execute(sa.text("UPDATE grupos_chat SET icone_chave = CASE WHEN is_direto = :t THEN 'message-circle' ELSE 'users' END "
                         "WHERE icone_chave IS NULL"), {"t": True})

    # saldo inicial no ledger: a soma do ledger passa a reproduzir exatamente o saldo atual de cada usuário
    for uid, moedas, xp in bind.execute(sa.text("SELECT id, moedas, xp FROM usuarios")).fetchall():
        if (moedas or 0) > 0:
            bind.execute(sa.text(
                "INSERT INTO carteira_lancamentos (usuario_id, tipo, categoria, valor, saldo_apos, referencia_tipo, "
                "chave_idempotencia, descricao, origem, criado_em) "
                "SELECT :u, 'credito', 'saldo_inicial', :v, :v, 'migracao', :k, 'Saldo anterior à nova carteira', 'sistema', :t "
                "WHERE NOT EXISTS (SELECT 1 FROM carteira_lancamentos WHERE chave_idempotencia = :k)"),
                {"u": uid, "v": moedas, "k": f"saldo_inicial:{uid}", "t": agora})
        if (xp or 0) > 0:
            bind.execute(sa.text(
                "INSERT INTO xp_eventos (usuario_id, valor, origem, referencia, chave, criado_em) "
                "SELECT :u, :v, 'saldo_inicial', 'migracao', :k, :t "
                "WHERE NOT EXISTS (SELECT 1 FROM xp_eventos WHERE chave = :k)"),
                {"u": uid, "v": xp, "k": f"saldo_inicial:{uid}", "t": agora})


def downgrade():
    # Intencionalmente não suportado: reverter apagaria carteira, pagamentos e histórico.
    # Para voltar atrás, restaure o backup do banco feito antes do upgrade.
    raise RuntimeError("Downgrade não suportado (restaure o backup do banco).")
