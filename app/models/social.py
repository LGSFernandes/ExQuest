from app import clock
from app.extensions import db


class Amizade(db.Model):
    __tablename__ = "amizades"
    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    destinatario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    status = db.Column(db.String(20), default="pendente")  # pendente | aceito | recusado
    favorito_sol = db.Column(db.Boolean, default=False)
    favorito_dest = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    solicitante = db.relationship("Usuario", foreign_keys=[solicitante_id])
    destinatario = db.relationship("Usuario", foreign_keys=[destinatario_id])
    __table_args__ = (
        db.Index("uq_amizade_par", "solicitante_id", "destinatario_id", unique=True),
        db.Index("ix_amizade_dest", "destinatario_id", "status"),
    )


class GrupoChat(db.Model):
    __tablename__ = "grupos_chat"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    icone = db.Column(db.String(50))  # legado (emoji)
    icone_chave = db.Column(db.String(40), default="message")
    criador_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    is_direto = db.Column(db.Boolean, default=False)
    criador = db.relationship("Usuario", foreign_keys=[criador_id])
    membros = db.relationship("GrupoMembro", backref="grupo", cascade="all, delete-orphan", lazy="dynamic")
    mensagens = db.relationship("Mensagem", backref="grupo", cascade="all, delete-orphan", lazy="dynamic")


class GrupoMembro(db.Model):
    __tablename__ = "grupo_membros"
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_chat.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    eh_admin = db.Column(db.Boolean, default=False)
    favorito = db.Column(db.Boolean, default=False)
    ultima_atividade = db.Column(db.DateTime, default=clock.agora)
    entrou_em = db.Column(db.DateTime, default=clock.agora)
    usuario = db.relationship("Usuario")
    __table_args__ = (
        db.Index("uq_grupo_membro", "grupo_id", "usuario_id", unique=True),
        db.Index("ix_grupo_membro_usuario", "usuario_id"),
    )


class GrupoConfig(db.Model):  # tabela legada, sem uso
    __tablename__ = "grupo_configs"
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_chat.id"), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=True)
    icone = db.Column(db.String(50))


class Mensagem(db.Model):
    __tablename__ = "mensagens"
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_chat.id"), nullable=False)
    remetente_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    conteudo = db.Column(db.Text, nullable=True)
    imagem_path = db.Column(db.String(200), nullable=True)  # nome do arquivo anexado (imagem ou documento)
    tipo = db.Column(db.String(20), default="texto")  # texto | imagem | arquivo
    enviado_em = db.Column(db.DateTime, default=clock.agora)
    deletado = db.Column(db.Boolean, default=False)
    remetente = db.relationship("Usuario", foreign_keys=[remetente_id])
    __table_args__ = (db.Index("ix_mensagens_grupo", "grupo_id", "id"), db.Index("ix_mensagens_remetente", "remetente_id", "enviado_em"))


class Bloqueio(db.Model):
    __tablename__ = "bloqueios"
    id = db.Column(db.Integer, primary_key=True)
    bloqueador_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    bloqueado_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    criado_em = db.Column(db.DateTime, default=clock.agora)
    __table_args__ = (db.Index("uq_bloqueio_par", "bloqueador_id", "bloqueado_id", unique=True),)


class Denuncia(db.Model):
    __tablename__ = "denuncias"
    id = db.Column(db.Integer, primary_key=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    alvo_tipo = db.Column(db.String(20), nullable=False)  # usuario | mensagem | questao | resposta_suspeita
    alvo_id = db.Column(db.Integer, nullable=False)
    motivo = db.Column(db.String(40), nullable=False)
    detalhe = db.Column(db.String(500))
    status = db.Column(db.String(20), default="aberta", nullable=False)  # aberta | procedente | improcedente | arquivada
    resolvida_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    resolvida_em = db.Column(db.DateTime)
    nota_admin = db.Column(db.String(500))
    criado_em = db.Column(db.DateTime, default=clock.agora)
    autor = db.relationship("Usuario", foreign_keys=[autor_id])
    __table_args__ = (db.Index("ix_denuncias_status", "status", "criado_em"),)


class Notificacao(db.Model):
    __tablename__ = "notificacoes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo = db.Column(db.String(40), nullable=False)
    titulo = db.Column(db.String(120), nullable=False)
    corpo = db.Column(db.String(300))
    url = db.Column(db.String(200))
    origem_id = db.Column(db.Integer, index=True)  # quem gerou o aviso (para anonimizar na exclusão da conta)
    lida = db.Column(db.Boolean, default=False, nullable=False)
    criado_em = db.Column(db.DateTime, default=clock.agora, nullable=False)
    __table_args__ = (db.Index("ix_notif_usuario", "usuario_id", "lida", "criado_em"),)
