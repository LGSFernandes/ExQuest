from app import clock
from app.extensions import db


class LogAuditoria(db.Model):
    __tablename__ = "log_auditoria"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    acao = db.Column(db.String(100), nullable=False)
    detalhe = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(300), nullable=True)
    resultado = db.Column(db.String(20), default="ok")
    criado_em = db.Column(db.DateTime, default=clock.agora)
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    __table_args__ = (db.Index("ix_log_criado", "criado_em"), db.Index("ix_log_acao", "acao", "criado_em"))


class ConteudoBloqueado(db.Model):
    __tablename__ = "conteudo_bloqueado"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    tipo = db.Column(db.String(50), nullable=False)
    referencia = db.Column(db.String(200), nullable=True)
    motivo = db.Column(db.String(200), nullable=True)
    resolvido = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=clock.agora)


class TokenRecuperacao(db.Model):
    """`token` guarda o SHA-256 do token enviado por e-mail (tokens antigos em claro continuam válidos até expirar)."""
    __tablename__ = "tokens_recuperacao"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    token = db.Column(db.String(200), unique=True, nullable=False)
    expira = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    usuario = db.relationship("Usuario")
    __table_args__ = (db.Index("ix_tokens_usuario_usado", "usuario_id", "usado"),)

    @property
    def valido(self):
        return not self.usado and clock.agora() < self.expira
