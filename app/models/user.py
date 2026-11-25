from flask_login import UserMixin

from app import clock
from app.extensions import db, login_manager
from app.services import niveis, plans


@login_manager.user_loader
def load_user(user_id):
    """O identificador da sessão/cookie "lembrar" é `id:session_version`: trocar a senha ou "sair de todos" invalida os dois."""
    try:
        uid, versao = str(user_id).split(":")
        u = db.session.get(Usuario, int(uid))
        versao = int(versao)
    except (TypeError, ValueError):
        return None
    if u is None or u.is_banido or (u.session_version or 0) != versao:
        return None
    return u


class Usuario(db.Model, UserMixin):
    __tablename__ = "usuarios"

    def get_id(self):
        return f"{self.id}:{self.session_version or 0}"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    sobrenome = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(40), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=True)  # nulo: conta criada via Google
    tag = db.Column(db.String(10), unique=True, nullable=False)
    tag_custom = db.Column(db.String(10), unique=True, nullable=True)
    google_id = db.Column(db.String(200), unique=True, nullable=True)

    icon_path = db.Column(db.String(200), default=None)
    icon_emoji = db.Column(db.String(50), default="avatar_1")  # legado: chave do avatar predefinido (avatar_1..8)
    banner_path = db.Column(db.String(200), default=None)
    biografia = db.Column(db.String(300), default="")
    estilo_perfil = db.Column(db.String(30), default="padrao")

    nick_cor = db.Column(db.String(50), default=None)
    nick_gradiente = db.Column(db.String(100), default=None)
    nick_fonte = db.Column(db.String(50), default=None)

    xp = db.Column(db.Integer, default=0)
    moedas = db.Column(db.Integer, default=0)  # saldo desnormalizado; a verdade é carteira_lancamentos
    borda_ativa = db.Column(db.String(100), default=None)
    badge_ativa = db.Column(db.String(100), default=None)
    efeito_ativo = db.Column(db.String(100), default=None)
    fundo_ativo = db.Column(db.String(100), default=None)
    titulo_ativo = db.Column(db.String(100), default=None)
    nome_fx_ativo = db.Column(db.String(100), default=None)
    tema_ativo = db.Column(db.String(100), default=None)

    boost_xp_pct = db.Column(db.Integer, default=0)
    boost_xp_expira = db.Column(db.DateTime, default=None)
    boost_coin_pct = db.Column(db.Integer, default=0)
    boost_coin_expira = db.Column(db.DateTime, default=None)

    plano_premium = db.Column(db.String(20), default=None)
    premium_expira = db.Column(db.DateTime, default=None)
    premium_ciclo = db.Column(db.String(10), default=None)
    premium_cancelar_em = db.Column(db.DateTime, default=None)

    mostrar_stats = db.Column(db.Boolean, default=True)
    mostrar_historico = db.Column(db.Boolean, default=True)
    mostrar_amigos = db.Column(db.Boolean, default=True)
    perfil_publico = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())  # visível (e indexável) sem login

    questoes_hoje = db.Column(db.Integer, default=0)
    simulados_hoje = db.Column(db.Integer, default=0)
    questoes_bonus = db.Column(db.Integer, default=0, nullable=False, server_default="0")  # respostas extras ganhas em missões
    ultimo_reset = db.Column(db.Date, default=clock.hoje)

    is_admin = db.Column(db.Boolean, default=False)
    is_banido = db.Column(db.Boolean, default=False)
    session_version = db.Column(db.Integer, default=0, nullable=False, server_default="0")  # incrementar derruba todas as sessões
    censurar_conteudo = db.Column(db.Boolean, default=False)
    bloquear_pedidos_amizade = db.Column(db.Boolean, default=False)
    trial_ofertado = db.Column(db.Boolean, default=False)
    primeira_compra_moedas = db.Column(db.Boolean, default=False)
    torneios_este_mes = db.Column(db.Integer, default=0)
    ultimo_reset_torneios = db.Column(db.Date, default=clock.hoje)
    criado_em = db.Column(db.DateTime, default=clock.agora)

    streak = db.relationship("Streak", backref="usuario", uselist=False, cascade="all, delete-orphan")

    @property
    def nome_completo(self):
        return f"{self.nome} {self.sobrenome}"

    @property
    def tag_exibida(self):
        return self.tag_custom or self.tag

    # ── planos / direitos ────────────────────────────
    @property
    def premium_ativo(self):
        if self.is_admin:
            return True
        return bool(self.plano_premium and self.premium_expira and clock.agora() < self.premium_expira)

    @property
    def plano_efetivo(self):
        if self.is_admin:
            return "advan"
        return self.plano_premium if self.premium_ativo else None

    def limite(self, chave):
        return plans.limite(chave, self.plano_efetivo)

    def pode(self, recurso):
        return plans.recurso(recurso, self.plano_efetivo)

    limite_questoes_dia = property(lambda s: s.limite("questoes_dia"))
    limite_simulados_dia = property(lambda s: s.limite("simulados_dia"))
    max_questoes_simulado = property(lambda s: s.limite("max_questoes_simulado"))
    limite_amigos = property(lambda s: s.limite("amigos"))
    limite_grupos = property(lambda s: s.limite("grupos"))
    limite_torneios_mes = property(lambda s: s.limite("torneios_mes"))
    pode_competicoes = property(lambda s: s.pode("competicoes"))
    pode_upload_banner = property(lambda s: s.pode("upload_banner"))
    pode_upload_gif = property(lambda s: s.pode("upload_gif"))
    pode_nick_cor = property(lambda s: s.pode("nick_cor"))
    pode_nick_gradiente = property(lambda s: s.pode("nick_gradiente"))
    pode_nick_fonte = property(lambda s: s.pode("nick_fonte"))
    pode_tag_custom = property(lambda s: s.pode("tag_custom"))

    @property
    def boost_xp_atual(self):
        extra = self.boost_xp_pct if self.boost_xp_expira and clock.agora() < self.boost_xp_expira else 0
        return self.limite("boost_pct") + (extra or 0)

    @property
    def boost_moeda_atual(self):
        extra = self.boost_coin_pct if self.boost_coin_expira and clock.agora() < self.boost_coin_expira else 0
        return self.limite("boost_pct") + (extra or 0)

    # ── nível ────────────────────────────────────────
    @property
    def nivel(self):
        return niveis.nivel_por_xp(self.xp or 0)

    @property
    def xp_para_proximo_nivel(self):
        return niveis.xp_proximo_nivel(self.nivel)

    @property
    def xp_nivel_atual(self):
        return niveis.xp_inicio_do_nivel(self.nivel)

    @property
    def progresso_nivel(self):
        return niveis.progresso(self.xp or 0)

    def __repr__(self):
        return f"<Usuario {self.username}#{self.tag}>"

    __table_args__ = (db.Index("ix_usuarios_ranking", "is_banido", "xp"),)  # ranking global e destaques da home: ordenam por XP entre não banidos


class Streak(db.Model):
    __tablename__ = "streaks"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    sequencia_atual = db.Column(db.Integer, default=0)
    maior_sequencia = db.Column(db.Integer, default=0)
    ultima_atividade = db.Column(db.Date, nullable=True)
    streak_protegido = db.Column(db.Boolean, default=False)  # legado (equivale a 1 escudo)
    escudos = db.Column(db.Integer, default=0, nullable=False, server_default="0")
    __table_args__ = (db.Index("uq_streaks_usuario", "usuario_id", unique=True),)
