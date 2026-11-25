import json

from app import clock
from app.extensions import db

TORNEIO_CONFIG = {
    "micro":   {"questoes": 5,  "tempo_min": 10,  "label": "Micro"},
    "pequeno": {"questoes": 10, "tempo_min": 20,  "label": "Pequeno"},
    "medio":   {"questoes": 20, "tempo_min": 40,  "label": "Médio"},
    "grande":  {"questoes": 35, "tempo_min": 70,  "label": "Grande"},
    "mega":    {"questoes": 50, "tempo_min": 100, "label": "Mega"},
}


class Torneio(db.Model):
    __tablename__ = "torneios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    tipo = db.Column(db.String(20), default="pequeno")
    materias_json = db.Column(db.Text, default="[]")
    dificuldades_json = db.Column(db.Text, default="[]")
    num_questoes = db.Column(db.Integer, default=10)
    tempo_minutos = db.Column(db.Integer, default=20)  # tempo que cada participante tem após começar
    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="aberto")  # aberto | finalizado | cancelado
    recompensa_xp_1 = db.Column(db.Integer, default=500)
    recompensa_xp_2 = db.Column(db.Integer, default=300)
    recompensa_xp_3 = db.Column(db.Integer, default=150)
    recompensa_moedas_1 = db.Column(db.Integer, default=200)
    recompensa_moedas_2 = db.Column(db.Integer, default=100)
    recompensa_moedas_3 = db.Column(db.Integer, default=50)
    badge_temp = db.Column(db.String(50), nullable=True)
    finalizado_em = db.Column(db.DateTime, nullable=True)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    __table_args__ = (db.Index("ix_torneios_status_fim", "status", "fim"), db.Index("ix_torneios_inicio", "inicio"))

    @property
    def config(self):
        return TORNEIO_CONFIG.get(self.tipo, TORNEIO_CONFIG["pequeno"])

    @property
    def materias_ids(self):
        try:
            return [int(x) for x in json.loads(self.materias_json or "[]")]
        except (ValueError, TypeError):
            return []

    @property
    def dificuldades_list(self):
        try:
            return list(json.loads(self.dificuldades_json or "[]"))
        except (ValueError, TypeError):
            return []

    @property
    def fase(self):
        """agendado | em_andamento | encerrado (por tempo) | finalizado (prêmios pagos) | cancelado"""
        if self.status in ("finalizado", "cancelado"):
            return self.status
        agora = clock.agora()
        if agora < self.inicio:
            return "agendado"
        return "em_andamento" if agora < self.fim else "encerrado"


class TorneioQuestao(db.Model):
    """Conjunto FIXO de questões do torneio, sorteado uma vez na criação."""
    __tablename__ = "torneio_questoes"
    id = db.Column(db.Integer, primary_key=True)
    torneio_id = db.Column(db.Integer, db.ForeignKey("torneios.id"), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey("questoes.id"), nullable=False)
    ordem = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.Index("uq_torneio_questao", "torneio_id", "questao_id", unique=True),)


class TorneioParticipante(db.Model):
    __tablename__ = "torneio_participantes"
    id = db.Column(db.Integer, primary_key=True)
    torneio_id = db.Column(db.Integer, db.ForeignKey("torneios.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    pontuacao = db.Column(db.Integer, default=0)
    acertos = db.Column(db.Integer, default=0)
    respondidas = db.Column(db.Integer, default=0)
    finalizado = db.Column(db.Boolean, default=False)
    posicao = db.Column(db.Integer, nullable=True)
    recompensa_paga = db.Column(db.Boolean, default=False)
    entrou_em = db.Column(db.DateTime, default=clock.agora)
    iniciou_em = db.Column(db.DateTime, nullable=True)
    terminou_em = db.Column(db.DateTime, nullable=True)
    usuario = db.relationship("Usuario")
    torneio = db.relationship("Torneio")
    __table_args__ = (
        db.Index("uq_torneio_participante", "torneio_id", "usuario_id", unique=True),
        db.Index("ix_torneio_part_usuario", "usuario_id"),
    )


class TorneioResposta(db.Model):
    __tablename__ = "torneio_respostas"
    id = db.Column(db.Integer, primary_key=True)
    torneio_id = db.Column(db.Integer, db.ForeignKey("torneios.id"), nullable=False)
    participante_id = db.Column(db.Integer, db.ForeignKey("torneio_participantes.id"), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey("questoes.id"), nullable=False)
    alternativa_id = db.Column(db.Integer, db.ForeignKey("alternativas.id"), nullable=True)
    resposta_texto = db.Column(db.Text, nullable=True)
    acertou = db.Column(db.Boolean, nullable=False)
    respondido_em = db.Column(db.DateTime, default=clock.agora)
    __table_args__ = (db.Index("uq_torneio_resposta", "participante_id", "questao_id", unique=True),)
