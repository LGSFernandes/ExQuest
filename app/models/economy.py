import json

from app import clock
from app.extensions import db


class ItemLoja(db.Model):
    __tablename__ = "itens_loja"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), nullable=True)  # identidade estável do item no catálogo versionado
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(300), nullable=False)
    # borda | fundo | badge | efeito | titulo | nome_fx | tema | boost_xp | boost_moeda | streak_shield
    tipo = db.Column(db.String(30), nullable=False)
    raridade = db.Column(db.String(20), default="comum")  # comum | raro | epico | lendario
    preco = db.Column(db.Integer, nullable=False)
    imagem = db.Column(db.String(200), nullable=True)  # legado
    css_class = db.Column(db.String(100), nullable=True)  # classe CSS que implementa o visual
    valor_boost = db.Column(db.Integer, default=0)  # % do boost, ou nº de cargas do escudo
    duracao_h = db.Column(db.Integer, default=0)  # duração do efeito de um consumível
    duracao_dias = db.Column(db.Integer, nullable=True)  # cosmético temporário: validade após a compra
    config_json = db.Column(db.Text, nullable=True)  # texto do título, paleta do tema, etc.
    ordem = db.Column(db.Integer, default=0)
    disponivel_ate = db.Column(db.DateTime, nullable=True)  # item de evento
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=clock.agora)

    __table_args__ = (db.UniqueConstraint("slug", name="uq_itens_loja_slug"),)

    CONSUMIVEIS = ("boost_xp", "boost_moeda", "streak_shield")

    @property
    def eh_consumivel(self):
        return self.tipo in self.CONSUMIVEIS

    @property
    def config(self):
        try:
            return json.loads(self.config_json or "{}")
        except ValueError:
            return {}

    @property
    def disponivel(self):
        return bool(self.ativo and (self.disponivel_ate is None or clock.agora() < self.disponivel_ate))


class InventarioItem(db.Model):
    __tablename__ = "inventario"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("itens_loja.id"), nullable=False)
    quantidade = db.Column(db.Integer, default=1)
    equipado = db.Column(db.Boolean, default=False)
    comprado_em = db.Column(db.DateTime, default=clock.agora)
    expira_em = db.Column(db.DateTime, nullable=True)
    origem = db.Column(db.String(30), default="compra")  # compra | recompensa | admin
    item = db.relationship("ItemLoja", lazy="joined")
    __table_args__ = (db.Index("uq_inventario_usuario_item", "usuario_id", "item_id", unique=True),)

    @property
    def expirado(self):
        return bool(self.expira_em and clock.agora() >= self.expira_em)


class LancamentoCarteira(db.Model):
    """Ledger imutável de moedas. Nunca se edita nem apaga: correções são novos lançamentos."""
    __tablename__ = "carteira_lancamentos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # credito | debito
    categoria = db.Column(db.String(30), nullable=False)  # recompensa|compra_item|compra_moedas|bonus|estorno|reembolso|ajuste_admin|premio|missao|saldo_inicial
    valor = db.Column(db.Integer, nullable=False)  # sempre > 0
    saldo_apos = db.Column(db.Integer, nullable=False)
    referencia_tipo = db.Column(db.String(30))
    referencia_id = db.Column(db.String(64))
    chave_idempotencia = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.String(200))
    origem = db.Column(db.String(20), default="sistema")  # sistema | admin | provedor
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    criado_em = db.Column(db.DateTime, default=clock.agora, nullable=False)
    __table_args__ = (
        db.Index("uq_carteira_chave", "chave_idempotencia", unique=True),
        db.Index("ix_carteira_usuario_data", "usuario_id", "criado_em"),
    )


class XpEvento(db.Model):
    __tablename__ = "xp_eventos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    valor = db.Column(db.Integer, nullable=False)
    origem = db.Column(db.String(30), nullable=False)  # resposta | simulado | missao | torneio | nivel | saldo_inicial | ajuste_admin
    referencia = db.Column(db.String(64))
    chave = db.Column(db.String(120), nullable=False)
    criado_em = db.Column(db.DateTime, default=clock.agora, nullable=False)
    __table_args__ = (
        db.Index("uq_xp_eventos_chave", "chave", unique=True),
        db.Index("ix_xp_eventos_data", "criado_em", "usuario_id"),
        db.Index("ix_xp_eventos_usuario", "usuario_id"),
    )


class RecompensaNivelConcedida(db.Model):
    __tablename__ = "recompensas_nivel"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nivel = db.Column(db.Integer, nullable=False)
    concedida_em = db.Column(db.DateTime, default=clock.agora)
    __table_args__ = (db.Index("uq_recompensa_nivel", "usuario_id", "nivel", unique=True),)


class Pagamento(db.Model):
    """Pedido de dinheiro real. Só vira 'aprovado' depois de webhook verificado + consulta ao provedor."""
    __tablename__ = "pagamentos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # moedas | premium
    produto_ref = db.Column(db.String(60), nullable=False)  # id do pacote ou "plano:ciclo"
    descricao = db.Column(db.String(200))
    provider = db.Column(db.String(20), nullable=False)  # mercadopago | stripe
    provider_ref = db.Column(db.String(200))  # id do checkout/preferência
    provider_payment_id = db.Column(db.String(200))
    valor_centavos = db.Column(db.Integer, nullable=False)
    moeda = db.Column(db.String(3), default="BRL", nullable=False)
    status = db.Column(db.String(20), default="criado", nullable=False)  # criado|pendente|aprovado|recusado|cancelado|expirado|reembolsado|contestado|divergente
    moedas_total = db.Column(db.Integer)  # moedas a creditar (base + bônus) — só tipo=moedas
    bonus_primeira = db.Column(db.Boolean, default=False)
    plano = db.Column(db.String(20))
    ciclo = db.Column(db.String(10))
    chave_idempotencia = db.Column(db.String(120), nullable=False)
    observacao = db.Column(db.String(300))
    criado_em = db.Column(db.DateTime, default=clock.agora, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=clock.agora, onupdate=clock.agora)
    aprovado_em = db.Column(db.DateTime)
    reembolsado_em = db.Column(db.DateTime)
    __table_args__ = (
        db.Index("uq_pagamentos_chave", "chave_idempotencia", unique=True),
        db.Index("ix_pagamentos_usuario", "usuario_id", "criado_em"),
        db.Index("ix_pagamentos_provider_ref", "provider", "provider_ref"),
        db.Index("ix_pagamentos_provider_pay", "provider", "provider_payment_id"),
        db.Index("ix_pagamentos_status", "status", "criado_em"),
    )


class EventoWebhook(db.Model):
    """Dedupe de webhooks: o mesmo (provedor, evento) é processado uma única vez."""
    __tablename__ = "eventos_webhook"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(20), nullable=False)
    evento_id = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(80))
    resultado = db.Column(db.String(40))
    recebido_em = db.Column(db.DateTime, default=clock.agora, nullable=False)
    processado_em = db.Column(db.DateTime)
    __table_args__ = (db.Index("uq_evento_webhook", "provider", "evento_id", unique=True),)


class Assinatura(db.Model):
    __tablename__ = "assinaturas"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    plano = db.Column(db.String(20), nullable=False)
    ciclo = db.Column(db.String(10), nullable=False)
    gateway_ref = db.Column(db.String(200), nullable=True)  # legado
    status = db.Column(db.String(20), default="ativa")  # ativa|cancelada|expirada|inadimplente|reembolsada|trial
    inicio = db.Column(db.DateTime, default=clock.agora)
    expira = db.Column(db.DateTime, nullable=True)
    renovacao_auto = db.Column(db.Boolean, default=True)
    provider = db.Column(db.String(20))
    provider_assinatura_id = db.Column(db.String(200))
    cancelar_ao_fim = db.Column(db.Boolean, default=False)
    atualizado_em = db.Column(db.DateTime, default=clock.agora)
    __table_args__ = (db.Index("ix_assinaturas_usuario", "usuario_id", "status"), db.Index("ix_assinaturas_expira", "status", "expira"))


class OfertaTrial(db.Model):
    __tablename__ = "ofertas_trial"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    ofertado_em = db.Column(db.DateTime, default=clock.agora)
    aceito = db.Column(db.Boolean, default=False)
    aceito_em = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.Index("uq_trial_usuario", "usuario_id", unique=True),)


# ── Tabelas legadas: preservadas (dados históricos), sem uso em fluxos novos ─────────
class CompraMoedas(db.Model):
    __tablename__ = "compras_moedas"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    pacote_id = db.Column(db.String(30), nullable=False)
    moedas_base = db.Column(db.Integer, nullable=False)
    moedas_bonus = db.Column(db.Integer, default=0)
    valor_brl = db.Column(db.Float, nullable=False)
    gateway_ref = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default="pendente")
    eh_primeira = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=clock.agora)


class PagamentoHistorico(db.Model):
    __tablename__ = "pagamento_historico"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    plano = db.Column(db.String(20), nullable=False)
    ciclo = db.Column(db.String(10), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="pago")
    cartao_final = db.Column(db.String(4), nullable=True)  # não utilizado: dados de cartão nunca passam pelo ExQuest
    cartao_nome = db.Column(db.String(100), nullable=True)
    cartao_numero = db.Column(db.String(25), nullable=True)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    descricao = db.Column(db.String(200), nullable=True)


class AdsCredit(db.Model):
    """Legado do sistema de anúncios simulados (removido — ADR-006). Linhas antigas ficam preservadas."""
    __tablename__ = "ads_credits"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo = db.Column(db.String(20), default="video")
    questoes_extras = db.Column(db.Integer, default=2)
    usado = db.Column(db.Integer, default=0)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    expira_em = db.Column(db.DateTime)
