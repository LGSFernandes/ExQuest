from app import clock
from app.extensions import db


class MetricaRum(db.Model):
    """Métrica de velocidade medida no navegador do aluno (Core Web Vitals). Anônima: sem usuário, IP ou user-agent."""
    __tablename__ = "metricas_rum"
    id = db.Column(db.Integer, primary_key=True)
    rota = db.Column(db.String(60), nullable=False)       # nome do endpoint Flask (ex.: questoes.index), validado no servidor
    nome = db.Column(db.String(8), nullable=False)        # LCP | CLS | INP | FCP | TTFB
    valor = db.Column(db.Float, nullable=False)           # ms (CLS é adimensional)
    dispositivo = db.Column(db.String(8), nullable=False)  # movel | desktop
    conexao = db.Column(db.String(10), nullable=False, default="")  # effectiveType: 4g, 3g, 2g, slow-2g ou vazio
    criado_em = db.Column(db.DateTime, nullable=False, default=clock.agora)
    __table_args__ = (db.Index("ix_rum_rota", "rota", "nome", "criado_em"), db.Index("ix_rum_criado", "criado_em"))
