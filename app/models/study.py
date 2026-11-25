from app import clock
from app.extensions import db


class SimuladoSessao(db.Model):
    """Simulado persistido no servidor: a nota e o tempo não dependem do navegador."""
    __tablename__ = "simulado_sessoes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    token = db.Column(db.String(40), nullable=False)
    questoes_json = db.Column(db.Text, nullable=False)  # ids em ordem
    filtros_json = db.Column(db.Text)
    iniciado_em = db.Column(db.DateTime, default=clock.agora, nullable=False)
    limite_segundos = db.Column(db.Integer, nullable=False)
    finalizado_em = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="em_andamento", nullable=False)  # em_andamento | finalizado | expirado
    acertos = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    xp_total = db.Column(db.Integer, default=0)
    moedas_total = db.Column(db.Integer, default=0)
    __table_args__ = (
        db.Index("uq_simulado_token", "token", unique=True),
        db.Index("ix_simulado_usuario", "usuario_id", "iniciado_em"),
    )


class RevisaoQuestao(db.Model):
    """Fila de revisão espaçada (SM-2 simplificado) por usuário e questão."""
    __tablename__ = "revisoes_questao"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey("questoes.id"), nullable=False)
    facilidade = db.Column(db.Float, default=2.5, nullable=False)
    intervalo_dias = db.Column(db.Integer, default=0, nullable=False)
    repeticoes = db.Column(db.Integer, default=0, nullable=False)
    lapsos = db.Column(db.Integer, default=0, nullable=False)
    proxima_em = db.Column(db.DateTime, nullable=False)
    ultima_em = db.Column(db.DateTime)
    origem = db.Column(db.String(20), default="erro")  # erro | manual
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    questao = db.relationship("Questao", lazy="joined")
    __table_args__ = (
        db.Index("uq_revisao_usuario_questao", "usuario_id", "questao_id", unique=True),
        db.Index("ix_revisao_devida", "usuario_id", "ativo", "proxima_em"),
    )


class Colecao(db.Model):
    __tablename__ = "colecoes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nome = db.Column(db.String(80), nullable=False)
    eh_favoritos = db.Column(db.Boolean, default=False, nullable=False)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    itens = db.relationship("ColecaoItem", backref="colecao", cascade="all, delete-orphan", lazy="dynamic")
    __table_args__ = (db.Index("uq_colecao_nome", "usuario_id", "nome", unique=True),)


class ColecaoItem(db.Model):
    __tablename__ = "colecao_itens"
    id = db.Column(db.Integer, primary_key=True)
    colecao_id = db.Column(db.Integer, db.ForeignKey("colecoes.id"), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey("questoes.id"), nullable=False)
    adicionado_em = db.Column(db.DateTime, default=clock.agora)
    questao = db.relationship("Questao", lazy="joined")
    __table_args__ = (db.Index("uq_colecao_item", "colecao_id", "questao_id", unique=True),)


class MissaoProgresso(db.Model):
    __tablename__ = "missoes_progresso"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    missao_slug = db.Column(db.String(60), nullable=False)
    periodo_chave = db.Column(db.String(20), nullable=False)  # "2026-11-10" (diária) ou "2026-W46" (semanal)
    progresso = db.Column(db.Integer, default=0, nullable=False)
    meta = db.Column(db.Integer, nullable=False)
    concluida_em = db.Column(db.DateTime)
    resgatada_em = db.Column(db.DateTime)
    __table_args__ = (db.Index("uq_missao_periodo", "usuario_id", "missao_slug", "periodo_chave", unique=True),)
