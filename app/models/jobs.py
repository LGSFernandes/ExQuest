import json

from app import clock
from app.extensions import db


class Job(db.Model):
    """Tarefa lenta executada fora da requisição (e-mail, etc.). Ver app/services/jobs.py."""
    __tablename__ = "jobs"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(40), nullable=False)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    status = db.Column(db.String(12), nullable=False, default="pendente")  # pendente | executando | ok | morto
    tentativas = db.Column(db.Integer, nullable=False, default=0)
    max_tentativas = db.Column(db.Integer, nullable=False, default=5)
    proxima_em = db.Column(db.DateTime, nullable=False, default=clock.agora)
    iniciado_em = db.Column(db.DateTime, nullable=True)
    concluido_em = db.Column(db.DateTime, nullable=True)
    erro = db.Column(db.String(300), nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=clock.agora)
    __table_args__ = (db.Index("ix_jobs_fila", "status", "proxima_em"),)

    @property
    def payload(self) -> dict:
        try:
            return json.loads(self.payload_json or "{}")
        except ValueError:
            return {}
