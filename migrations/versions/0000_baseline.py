"""baseline: esquema original do ExQuest (anterior à versão 1.4)

Esta revisão recria o esquema que o projeto criava via `db.create_all()` antes de existir migração.
Ela permite `flask db upgrade` em banco vazio. No banco já existente (versão 62e588f5787b) ela NÃO é executada:
o Alembic parte da revisão registrada e aplica apenas as revisões seguintes.

Gerada por reflexão do banco real (cópia somente-leitura); as colunas das revisões 1.4, 1.5 e 1.6 foram
deliberadamente omitidas porque essas revisões as adicionam.

Revision ID: 0000_baseline
Revises:
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = '0000_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'itens_loja',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('descricao', sa.String(length=300), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('raridade', sa.String(length=20), nullable=True),
        sa.Column('preco', sa.Integer(), nullable=False),
        sa.Column('imagem', sa.String(length=200), nullable=True),
        sa.Column('css_class', sa.String(length=100), nullable=True),
        sa.Column('valor_boost', sa.Integer(), nullable=True),
        sa.Column('duracao_h', sa.Integer(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'materias',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('icone', sa.String(length=50), nullable=True),
        sa.Column('cor', sa.String(length=20), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('nome'),
    )
    op.create_table(
        'torneios',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('tipo', sa.String(length=20), nullable=True),
        sa.Column('materias_json', sa.Text(), nullable=True),
        sa.Column('dificuldades_json', sa.Text(), nullable=True),
        sa.Column('num_questoes', sa.Integer(), nullable=True),
        sa.Column('tempo_minutos', sa.Integer(), nullable=True),
        sa.Column('inicio', sa.DateTime(), nullable=False),
        sa.Column('fim', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('recompensa_xp_1', sa.Integer(), nullable=True),
        sa.Column('recompensa_xp_2', sa.Integer(), nullable=True),
        sa.Column('recompensa_xp_3', sa.Integer(), nullable=True),
        sa.Column('recompensa_moedas_1', sa.Integer(), nullable=True),
        sa.Column('recompensa_moedas_2', sa.Integer(), nullable=True),
        sa.Column('recompensa_moedas_3', sa.Integer(), nullable=True),
        sa.Column('badge_temp', sa.String(length=50), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'usuarios',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('nome', sa.String(length=80), nullable=False),
        sa.Column('sobrenome', sa.String(length=80), nullable=False),
        sa.Column('username', sa.String(length=40), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('senha_hash', sa.String(length=255), nullable=True),
        sa.Column('tag', sa.String(length=10), nullable=False),
        sa.Column('tag_custom', sa.String(length=10), nullable=True),
        sa.Column('google_id', sa.String(length=200), nullable=True),
        sa.Column('icon_path', sa.String(length=200), nullable=True),
        sa.Column('icon_emoji', sa.String(length=50), nullable=True),
        sa.Column('banner_path', sa.String(length=200), nullable=True),
        sa.Column('biografia', sa.String(length=300), nullable=True),
        sa.Column('estilo_perfil', sa.String(length=30), nullable=True),
        sa.Column('nick_cor', sa.String(length=50), nullable=True),
        sa.Column('nick_gradiente', sa.String(length=100), nullable=True),
        sa.Column('nick_fonte', sa.String(length=50), nullable=True),
        sa.Column('xp', sa.Integer(), nullable=True),
        sa.Column('moedas', sa.Integer(), nullable=True),
        sa.Column('borda_ativa', sa.String(length=100), nullable=True),
        sa.Column('badge_ativa', sa.String(length=100), nullable=True),
        sa.Column('efeito_ativo', sa.String(length=100), nullable=True),
        sa.Column('boost_xp_pct', sa.Integer(), nullable=True),
        sa.Column('boost_xp_expira', sa.DateTime(), nullable=True),
        sa.Column('boost_coin_pct', sa.Integer(), nullable=True),
        sa.Column('boost_coin_expira', sa.DateTime(), nullable=True),
        sa.Column('plano_premium', sa.String(length=20), nullable=True),
        sa.Column('premium_expira', sa.DateTime(), nullable=True),
        sa.Column('mostrar_stats', sa.Boolean(), nullable=True),
        sa.Column('mostrar_historico', sa.Boolean(), nullable=True),
        sa.Column('mostrar_amigos', sa.Boolean(), nullable=True),
        sa.Column('questoes_hoje', sa.Integer(), nullable=True),
        sa.Column('simulados_hoje', sa.Integer(), nullable=True),
        sa.Column('ultimo_reset', sa.Date(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=True),
        sa.Column('is_banido', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('google_id'),
        sa.UniqueConstraint('tag'),
        sa.UniqueConstraint('tag_custom'),
        sa.UniqueConstraint('username'),
    )
    op.create_table(
        'ads_credits',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=True),
        sa.Column('questoes_extras', sa.Integer(), nullable=True),
        sa.Column('usado', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('expira_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'amizades',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('solicitante_id', sa.Integer(), nullable=False),
        sa.Column('destinatario_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['destinatario_id'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['solicitante_id'], ['usuarios.id']),
    )
    op.create_table(
        'assinaturas',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('plano', sa.String(length=20), nullable=False),
        sa.Column('ciclo', sa.String(length=10), nullable=False),
        sa.Column('gateway_ref', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('inicio', sa.DateTime(), nullable=True),
        sa.Column('expira', sa.DateTime(), nullable=True),
        sa.Column('renovacao_auto', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'compras_moedas',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('pacote_id', sa.String(length=30), nullable=False),
        sa.Column('moedas_base', sa.Integer(), nullable=False),
        sa.Column('moedas_bonus', sa.Integer(), nullable=True),
        sa.Column('valor_brl', sa.Float(), nullable=False),
        sa.Column('gateway_ref', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('eh_primeira', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'conteudo_bloqueado',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('referencia', sa.String(length=200), nullable=True),
        sa.Column('motivo', sa.String(length=200), nullable=True),
        sa.Column('resolvido', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'grupos_chat',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('icone', sa.String(length=50), nullable=True),
        sa.Column('criador_id', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('is_direto', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['criador_id'], ['usuarios.id']),
    )
    op.create_table(
        'inventario',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=True),
        sa.Column('equipado', sa.Boolean(), nullable=True),
        sa.Column('comprado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['item_id'], ['itens_loja.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'log_auditoria',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('acao', sa.String(length=100), nullable=False),
        sa.Column('detalhe', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=300), nullable=True),
        sa.Column('resultado', sa.String(length=20), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'ofertas_trial',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('ofertado_em', sa.DateTime(), nullable=True),
        sa.Column('aceito', sa.Boolean(), nullable=True),
        sa.Column('aceito_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'pagamento_historico',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('plano', sa.String(length=20), nullable=False),
        sa.Column('ciclo', sa.String(length=10), nullable=False),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('cartao_final', sa.String(length=4), nullable=True),
        sa.Column('cartao_nome', sa.String(length=100), nullable=True),
        sa.Column('cartao_numero', sa.String(length=25), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('descricao', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'questoes',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('enunciado', sa.Text(), nullable=False),
        sa.Column('explicacao', sa.Text(), nullable=True),
        sa.Column('dificuldade', sa.String(length=10), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=True),
        sa.Column('resposta_correta', sa.Text(), nullable=True),
        sa.Column('materia_id', sa.Integer(), nullable=False),
        sa.Column('imagem_path', sa.String(length=200), nullable=True),
        sa.Column('conteudo', sa.String(length=100), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['materia_id'], ['materias.id']),
    )
    op.create_table(
        'recompensas_nivel',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('nivel', sa.Integer(), nullable=False),
        sa.Column('concedida_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'streaks',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('sequencia_atual', sa.Integer(), nullable=True),
        sa.Column('maior_sequencia', sa.Integer(), nullable=True),
        sa.Column('ultima_atividade', sa.Date(), nullable=True),
        sa.Column('streak_protegido', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'tokens_recuperacao',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=200), nullable=False),
        sa.Column('expira', sa.DateTime(), nullable=False),
        sa.Column('usado', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.UniqueConstraint('token'),
    )
    op.create_table(
        'torneio_participantes',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('torneio_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('pontuacao', sa.Integer(), nullable=True),
        sa.Column('acertos', sa.Integer(), nullable=True),
        sa.Column('respondidas', sa.Integer(), nullable=True),
        sa.Column('finalizado', sa.Boolean(), nullable=True),
        sa.Column('posicao', sa.Integer(), nullable=True),
        sa.Column('recompensa_paga', sa.Boolean(), nullable=True),
        sa.Column('entrou_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['torneio_id'], ['torneios.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'alternativas',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('texto', sa.Text(), nullable=False),
        sa.Column('correta', sa.Boolean(), nullable=False),
        sa.Column('questao_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['questao_id'], ['questoes.id']),
    )
    op.create_table(
        'grupo_configs',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('grupo_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=True),
        sa.Column('icone', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['grupo_id'], ['grupos_chat.id']),
        sa.UniqueConstraint('grupo_id'),
    )
    op.create_table(
        'grupo_membros',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('grupo_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('eh_admin', sa.Boolean(), nullable=True),
        sa.Column('entrou_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['grupo_id'], ['grupos_chat.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'mensagens',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('grupo_id', sa.Integer(), nullable=False),
        sa.Column('remetente_id', sa.Integer(), nullable=False),
        sa.Column('conteudo', sa.Text(), nullable=True),
        sa.Column('imagem_path', sa.String(length=200), nullable=True),
        sa.Column('tipo', sa.String(length=20), nullable=True),
        sa.Column('enviado_em', sa.DateTime(), nullable=True),
        sa.Column('deletado', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['grupo_id'], ['grupos_chat.id']),
        sa.ForeignKeyConstraint(['remetente_id'], ['usuarios.id']),
    )
    op.create_table(
        'questoes_respondidas_sessao',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('questao_id', sa.Integer(), nullable=False),
        sa.Column('sessao_id', sa.String(length=64), nullable=False),
        sa.Column('respondida_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['questao_id'], ['questoes.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'respostas_usuarios',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('questao_id', sa.Integer(), nullable=False),
        sa.Column('alternativa_id', sa.Integer(), nullable=True),
        sa.Column('resposta_texto', sa.Text(), nullable=True),
        sa.Column('acertou', sa.Boolean(), nullable=False),
        sa.Column('feedback_ia', sa.Text(), nullable=True),
        sa.Column('nota_ia', sa.Float(), nullable=True),
        sa.Column('xp_ganho', sa.Integer(), nullable=True),
        sa.Column('moedas_ganhas', sa.Integer(), nullable=True),
        sa.Column('modo', sa.String(length=20), nullable=True),
        sa.Column('data_resposta', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['alternativa_id'], ['alternativas.id']),
        sa.ForeignKeyConstraint(['questao_id'], ['questoes.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
    )
    op.create_table(
        'torneio_respostas',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('torneio_id', sa.Integer(), nullable=False),
        sa.Column('participante_id', sa.Integer(), nullable=False),
        sa.Column('questao_id', sa.Integer(), nullable=False),
        sa.Column('alternativa_id', sa.Integer(), nullable=True),
        sa.Column('resposta_texto', sa.Text(), nullable=True),
        sa.Column('acertou', sa.Boolean(), nullable=False),
        sa.Column('respondido_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['alternativa_id'], ['alternativas.id']),
        sa.ForeignKeyConstraint(['participante_id'], ['torneio_participantes.id']),
        sa.ForeignKeyConstraint(['questao_id'], ['questoes.id']),
        sa.ForeignKeyConstraint(['torneio_id'], ['torneios.id']),
    )


def downgrade():
    # Intencionalmente irreversível: derrubar o esquema original apagaria todos os dados.
    raise RuntimeError("O baseline não é reversível (evita perda total de dados).")
