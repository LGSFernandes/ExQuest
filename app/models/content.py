from app import clock
from app.extensions import db


class Materia(db.Model):
    __tablename__ = "materias"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    icone = db.Column(db.String(50))  # legado (emoji). Não é mais usado na interface.
    icone_chave = db.Column(db.String(40), default="book")
    cor = db.Column(db.String(20), default="#c6f135")
    ativo = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())
    criado_em = db.Column(db.DateTime, default=clock.agora)
    questoes = db.relationship("Questao", backref="materia", lazy="dynamic")


class Questao(db.Model):
    __tablename__ = "questoes"
    id = db.Column(db.Integer, primary_key=True)
    enunciado = db.Column(db.Text, nullable=False)
    explicacao = db.Column(db.Text, nullable=True)
    dificuldade = db.Column(db.String(10), nullable=False, default="medio")
    tipo = db.Column(db.String(20), default="multipla")  # multipla | discursiva
    resposta_correta = db.Column(db.Text, nullable=True)  # gabarito das discursivas
    materia_id = db.Column(db.Integer, db.ForeignKey("materias.id"), nullable=False)
    imagem_path = db.Column(db.String(200), nullable=True)
    conteudo = db.Column(db.String(100), nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())
    criado_em = db.Column(db.DateTime, default=clock.agora)
    alternativas = db.relationship("Alternativa", backref="questao", cascade="all, delete-orphan", lazy="selectin",
                                   order_by="Alternativa.id")
    __table_args__ = (db.Index("ix_questoes_materia_dif", "materia_id", "dificuldade"),)

    @property
    def alternativa_correta(self):
        return next((a for a in self.alternativas if a.correta), None)

    FAIXA_XP = {"facil": (10, 20), "medio": (25, 40), "dificil": (50, 80)}
    FAIXA_MOEDAS = {"facil": (2, 4), "medio": (4, 7), "dificil": (7, 10)}

    @property
    def xp_recompensa(self):
        return self.FAIXA_XP.get(self.dificuldade, (10, 20))

    @property
    def moedas_recompensa(self):
        return self.FAIXA_MOEDAS.get(self.dificuldade, (2, 4))


class Alternativa(db.Model):
    __tablename__ = "alternativas"
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    correta = db.Column(db.Boolean, default=False, nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey("questoes.id"), nullable=False)
    __table_args__ = (db.Index("ix_alternativas_questao", "questao_id"),)


class RespostaUsuario(db.Model):
    __tablename__ = "respostas_usuarios"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey("questoes.id"), nullable=False)
    alternativa_id = db.Column(db.Integer, db.ForeignKey("alternativas.id"), nullable=True)
    resposta_texto = db.Column(db.Text, nullable=True)
    acertou = db.Column(db.Boolean, nullable=False)
    feedback_ia = db.Column(db.Text, nullable=True)  # legado do nome; é feedback do avaliador (local ou OpenAI)
    nota_ia = db.Column(db.Float, nullable=True)
    xp_ganho = db.Column(db.Integer, default=0)
    moedas_ganhas = db.Column(db.Integer, default=0)
    modo = db.Column(db.String(20), default="questao")  # questao | simulado | revisao
    simulado_id = db.Column(db.Integer, nullable=True)  # sem FK: coluna adicionada por ALTER em SQLite
    tempo_ms = db.Column(db.Integer, nullable=True)  # medido pelo servidor
    data_resposta = db.Column(db.DateTime, default=clock.agora, nullable=False)
    questao = db.relationship("Questao", lazy="joined")
    __table_args__ = (
        db.Index("ix_respostas_usuario_data", "usuario_id", "data_resposta"),
        db.Index("ix_respostas_usuario_questao", "usuario_id", "questao_id"),
        db.Index("ix_respostas_questao", "questao_id"),
    )


class QuestaoRespondidaSessao(db.Model):
    """Evita repetir questão dentro de uma sessão de prática avulsa."""
    __tablename__ = "questoes_respondidas_sessao"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey("questoes.id"), nullable=False)
    sessao_id = db.Column(db.String(64), nullable=False)
    respondida_em = db.Column(db.DateTime, default=clock.agora)
    __table_args__ = (db.Index("ix_qrs_usuario_sessao", "usuario_id", "sessao_id"),)
