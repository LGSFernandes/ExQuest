from datetime import datetime, timezone, date, timedelta
from flask_login import UserMixin
from app import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


def _aware_utc(dt):
    """Garante que um datetime vindo do banco esteja com tzinfo UTC.

    O SQLite/SQLAlchemy não preserva timezone: um datetime 'aware' gravado
    no banco volta como 'naive' ao ser lido de volta, o que quebra
    comparações diretas com datetime.now(timezone.utc). Como todos os
    datetimes desta aplicação são sempre gerados em UTC, é seguro apenas
    marcar o valor 'naive' como UTC aqui, sem alterar o que está salvo.
    """
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════
#  USUÁRIO
# ══════════════════════════════════════════════════════

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    sobrenome = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(40), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=True) # nullable: Google OAuth
    tag = db.Column(db.String(10), unique=True, nullable=False)
    tag_custom = db.Column(db.String(10), unique=True, nullable=True) # Advan: tag personalizada

    # OAuth
    google_id = db.Column(db.String(200), unique=True, nullable=True)

    # Mídia de perfil
    icon_path = db.Column(db.String(200), default=None)
    icon_emoji = db.Column(db.String(50), default='avatar_1')
    banner_path = db.Column(db.String(200), default=None)
    biografia = db.Column(db.String(300), default='')
    estilo_perfil = db.Column(db.String(30), default='padrao')

    # Customização do nick (Premium)
    nick_cor = db.Column(db.String(50), default=None) # Inter+: cor hex
    nick_gradiente = db.Column(db.String(100), default=None) # Advan: gradiente CSS
    nick_fonte = db.Column(db.String(50), default=None) # Advan: família de fonte

    # Gamificação
    xp = db.Column(db.Integer, default=0)
    moedas = db.Column(db.Integer, default=0)
    borda_ativa = db.Column(db.String(100), default=None)
    badge_ativa = db.Column(db.String(100), default=None)
    efeito_ativo = db.Column(db.String(100), default=None)

    # Boosts temporários
    boost_xp_pct = db.Column(db.Integer, default=0)
    boost_xp_expira = db.Column(db.DateTime, default=None)
    boost_coin_pct = db.Column(db.Integer, default=0)
    boost_coin_expira = db.Column(db.DateTime, default=None)

    # Premium
    plano_premium = db.Column(db.String(20), default=None)
    premium_expira = db.Column(db.DateTime, default=None)
    premium_ciclo = db.Column(db.String(10), default=None) # mensal/anual
    premium_cancelar_em = db.Column(db.DateTime, default=None) # agendado para cancelar

    # Privacidade
    mostrar_stats = db.Column(db.Boolean, default=True)
    mostrar_historico = db.Column(db.Boolean, default=True)
    mostrar_amigos = db.Column(db.Boolean, default=True)

    # Limites diários
    questoes_hoje = db.Column(db.Integer, default=0)
    simulados_hoje = db.Column(db.Integer, default=0)
    ultimo_reset = db.Column(db.Date, default=lambda: date.today())

    # Controle
    is_admin = db.Column(db.Boolean, default=False)
    is_banido = db.Column(db.Boolean, default=False)
    # Configurações extras
    censurar_conteudo = db.Column(db.Boolean, default=False) # censura palavrões em chat
    bloquear_pedidos_amizade = db.Column(db.Boolean, default=False) # não receber pedidos de amizade
    # Trial / Oferta
    trial_ofertado = db.Column(db.Boolean, default=False)
    primeira_compra_moedas = db.Column(db.Boolean, default=False) # controle de bônus primeira compra
    # Competições
    torneios_este_mes = db.Column(db.Integer, default=0)
    ultimo_reset_torneios = db.Column(db.Date, default=lambda: date.today())
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    streak = db.relationship('Streak', backref='usuario', uselist=False,
                                    cascade='all, delete-orphan')
    respostas = db.relationship('RespostaUsuario', backref='usuario',
                                    cascade='all, delete-orphan', lazy='dynamic')
    inventario = db.relationship('InventarioItem', backref='usuario',
                                    cascade='all, delete-orphan', lazy='dynamic')
    mensagens_env = db.relationship('Mensagem', foreign_keys='Mensagem.remetente_id',
                                    backref='remetente', lazy='dynamic')
    assinaturas = db.relationship('Assinatura', backref='usuario',
                                    cascade='all, delete-orphan', lazy='dynamic')

    # ── Propriedades ────────────────────────────────

    @property
    def nome_completo(self):
        return f'{self.nome} {self.sobrenome}'

    @property
    def tag_exibida(self):
        return self.tag_custom or self.tag

    @property
    def icon(self):
        return self.icon_path or self.icon_emoji

    @property
    def plano_efetivo(self):
        """Admin sempre tem plano advan para fins de acesso."""
        if self.is_admin:
            return 'advan'
        if self.premium_ativo:
            return self.plano_premium
        return None

    @property
    def premium_ativo(self):
        if self.is_admin:
            return True
        if not self.plano_premium or not self.premium_expira:
            return False
        return datetime.now(timezone.utc) < _aware_utc(self.premium_expira)

    @property
    def limite_questoes_dia(self):
        p = self.plano_efetivo
        if p is None:    return 3
        if p == 'basic': return 15
        if p == 'inter': return 30
        return None

    @property
    def limite_simulados_dia(self):
        p = self.plano_efetivo
        if p is None:    return 1
        if p == 'basic': return 3
        if p == 'inter': return 7
        return None

    @property
    def max_questoes_simulado(self):
        p = self.plano_efetivo
        if p is None:    return 5
        if p == 'basic': return 15
        if p == 'inter': return 20
        return 50  # advan

    @property
    def tem_ads(self):
        return self.plano_efetivo is None

    @property
    def pode_competicoes(self):
        return self.plano_efetivo in ('inter', 'advan') or self.is_admin

    @property
    def limite_torneios_mes(self):
        p = self.plano_efetivo
        if p is None:    return 0
        if p == 'basic': return 0
        if p == 'inter': return 3
        return None

    @property
    def limite_amigos(self):
        p = self.plano_efetivo
        if p is None:   return 15
        if p == 'basic': return 50
        if p == 'inter': return 100
        return None

    @property
    def limite_grupos(self):
        p = self.plano_efetivo
        if p is None:   return 5
        if p == 'basic': return 20
        if p == 'inter': return 40
        return None

    @property
    def boost_xp_atual(self):
        base = 0
        p = self.plano_efetivo
        if p:
            base = {'basic': 10, 'inter': 15, 'advan': 30}.get(p, 0)
        extra = 0
        if self.boost_xp_expira and datetime.now(timezone.utc) < _aware_utc(self.boost_xp_expira):
            extra = self.boost_xp_pct
        return base + extra

    @property
    def boost_moeda_atual(self):
        base = 0
        p = self.plano_efetivo
        if p:
            base = {'basic': 10, 'inter': 15, 'advan': 30}.get(p, 0)
        extra = 0
        if self.boost_coin_expira and datetime.now(timezone.utc) < _aware_utc(self.boost_coin_expira):
            extra = self.boost_coin_pct
        return base + extra

    @property
    def pode_upload_banner(self):
        return self.plano_efetivo in ('inter', 'advan')

    @property
    def pode_nick_cor(self):
        return self.plano_efetivo in ('inter', 'advan')

    @property
    def pode_nick_gradiente(self):
        return self.plano_efetivo == 'advan'

    @property
    def pode_nick_fonte(self):
        return self.plano_efetivo == 'advan'

    @property
    def pode_tag_custom(self):
        return self.plano_efetivo == 'advan'

    @property
    def nick_style(self):
        """Retorna o style CSS inline para o nick."""
        if self.nick_gradiente and self.pode_nick_gradiente:
            return (f'background:{self.nick_gradiente};'
                    f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
                    f'background-clip:text;')
        if self.nick_cor and self.pode_nick_cor:
            return f'color:{self.nick_cor};'
        return ''

    @property
    def nick_font_family(self):
        fontes = {
            'serif':    'Georgia, serif',
            'mono':     '"Courier New", monospace',
            'neon':     '"Orbitron", sans-serif',
            'party':    '"Pacifico", cursive',
            'elegant':  '"Playfair Display", serif',
        }
        if self.nick_fonte and self.pode_nick_fonte:
            return fontes.get(self.nick_fonte, '')
        return ''

    def resetar_diario_se_necessario(self):
        hoje = date.today()
        if self.ultimo_reset != hoje:
            self.questoes_hoje  = 0
            self.simulados_hoje = 0
            self.ultimo_reset   = hoje

    def pode_responder_questao(self):
        self.resetar_diario_se_necessario()
        lim = self.limite_questoes_dia
        return lim is None or self.questoes_hoje < lim

    def pode_fazer_simulado(self):
        self.resetar_diario_se_necessario()
        lim = self.limite_simulados_dia
        return lim is None or self.simulados_hoje < lim

    @property
    def nivel(self):
        if self.xp < 100:   return 1
        if self.xp < 300:   return 2
        if self.xp < 600:   return 3
        if self.xp < 1000:  return 4
        if self.xp < 1500:  return 5
        if self.xp < 2500:  return 6
        if self.xp < 4000:  return 7
        if self.xp < 6000:  return 8
        if self.xp < 9000:  return 9
        return 10

    @property
    def xp_para_proximo_nivel(self):
        return [100,300,600,1000,1500,2500,4000,6000,9000,99999][min(self.nivel-1,9)]

    @property
    def xp_nivel_atual(self):
        return [0,100,300,600,1000,1500,2500,4000,6000,9000][min(self.nivel-1,9)]

    @property
    def progresso_nivel(self):
        base = self.xp_nivel_atual
        topo = self.xp_para_proximo_nivel
        if topo == base: return 100
        return int(((self.xp - base) / (topo - base)) * 100)

    @property
    def total_acertos(self):
        return self.respostas.filter_by(acertou=True).count()

    @property
    def total_respostas(self):
        return self.respostas.count()

    @property
    def percentual_acerto(self):
        t = self.total_respostas
        return 0 if t == 0 else round((self.total_acertos / t) * 100, 1)

    def __repr__(self):
        return f'<Usuario {self.username}#{self.tag}>'


# ══════════════════════════════════════════════════════
#  STREAK
# ══════════════════════════════════════════════════════

class Streak(db.Model):
    __tablename__ = 'streaks'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    sequencia_atual = db.Column(db.Integer, default=0)
    maior_sequencia = db.Column(db.Integer, default=0)
    ultima_atividade = db.Column(db.Date, nullable=True)
    streak_protegido = db.Column(db.Boolean, default=False)

    def atualizar(self):
        hoje = date.today()
        if self.ultima_atividade is None:
            self.sequencia_atual = 1
        elif self.ultima_atividade == hoje:
            return
        elif self.ultima_atividade == hoje - timedelta(days=1):
            self.sequencia_atual += 1
        else:
            if self.streak_protegido:
                self.streak_protegido = False
            else:
                self.sequencia_atual = 1
        self.ultima_atividade = hoje
        if self.sequencia_atual > self.maior_sequencia:
            self.maior_sequencia = self.sequencia_atual


# ══════════════════════════════════════════════════════
#  MATÉRIA / QUESTÃO
# ══════════════════════════════════════════════════════

class Materia(db.Model):
    __tablename__ = 'materias'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    icone = db.Column(db.String(50), default='\U0001F4DA')
    cor = db.Column(db.String(20), default='#6366f1')
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    questoes = db.relationship('Questao', backref='materia',
                                cascade='all, delete-orphan', lazy='dynamic')
    @property
    def total_questoes(self): return self.questoes.count()


class Questao(db.Model):
    __tablename__ = 'questoes'
    id = db.Column(db.Integer, primary_key=True)
    enunciado = db.Column(db.Text, nullable=False)
    explicacao = db.Column(db.Text, nullable=True)
    dificuldade = db.Column(db.String(10), nullable=False, default='medio')
    tipo = db.Column(db.String(20), default='multipla') # 'multipla' | 'discursiva'
    resposta_correta = db.Column(db.Text, nullable=True) # para discursivas
    materia_id = db.Column(db.Integer, db.ForeignKey('materias.id'), nullable=False)
    imagem_path = db.Column(db.String(200), nullable=True)
    conteudo = db.Column(db.String(100), nullable=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    alternativas = db.relationship('Alternativa', backref='questao',
                                   cascade='all, delete-orphan', lazy='select')
    respostas = db.relationship('RespostaUsuario', backref='questao',
                                   cascade='all, delete-orphan', lazy='dynamic')

    @property
    def alternativa_correta(self):
        for alt in self.alternativas:
            if alt.correta: return alt
        return None

    @property
    def xp_recompensa(self):
        return {'facil':(10,20),'medio':(25,40),'dificil':(50,80)}.get(self.dificuldade,(10,20))

    @property
    def moedas_recompensa(self):
        return {'facil':(2,4),'medio':(4,7),'dificil':(7,10)}.get(self.dificuldade,(2,4))


class Alternativa(db.Model):
    __tablename__ = 'alternativas'
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    correta = db.Column(db.Boolean, default=False, nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey('questoes.id'), nullable=False)


class RespostaUsuario(db.Model):
    __tablename__ = 'respostas_usuarios'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey('questoes.id'), nullable=False)
    alternativa_id = db.Column(db.Integer, db.ForeignKey('alternativas.id'), nullable=True)
    resposta_texto = db.Column(db.Text, nullable=True) # discursiva
    acertou = db.Column(db.Boolean, nullable=False)
    feedback_ia = db.Column(db.Text, nullable=True) # feedback da IA para discursiva
    nota_ia = db.Column(db.Float, nullable=True) # 0.0 a 1.0
    xp_ganho = db.Column(db.Integer, default=0)
    moedas_ganhas = db.Column(db.Integer, default=0)
    modo = db.Column(db.String(20), default='questao')
    data_resposta = db.Column(db.DateTime,
                               default=lambda: datetime.now(timezone.utc), nullable=False)


# ══════════════════════════════════════════════════════
#  LOJA / INVENTÁRIO
# ══════════════════════════════════════════════════════

class ItemLoja(db.Model):
    __tablename__ = 'itens_loja'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(300), nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    raridade= db.Column(db.String(20), default='comum')
    preco = db.Column(db.Integer, nullable=False)
    imagem = db.Column(db.String(200), nullable=True)
    css_class = db.Column(db.String(100), nullable=True)
    valor_boost = db.Column(db.Integer, default=0)
    duracao_h = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class InventarioItem(db.Model):
    __tablename__ = 'inventario'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('itens_loja.id'), nullable=False)
    quantidade = db.Column(db.Integer, default=1)
    equipado = db.Column(db.Boolean, default=False)
    comprado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    item = db.relationship('ItemLoja', backref='inventarios')


# ══════════════════════════════════════════════════════
#  SOCIAL
# ══════════════════════════════════════════════════════

class Amizade(db.Model):
    __tablename__ = 'amizades'
    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    destinatario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    status = db.Column(db.String(20), default='pendente')
    # Favoritar por cada lado
    favorito_sol = db.Column(db.Boolean, default=False) # solicitante favoritou
    favorito_dest = db.Column(db.Boolean, default=False) # destinatário favoritou
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    solicitante = db.relationship('Usuario', foreign_keys=[solicitante_id])
    destinatario = db.relationship('Usuario', foreign_keys=[destinatario_id])


class GrupoChat(db.Model):
    __tablename__ = 'grupos_chat'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    icone = db.Column(db.String(50), default='\U0001F4AC')
    criador_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_direto = db.Column(db.Boolean, default=False)
    criador = db.relationship('Usuario', foreign_keys=[criador_id])
    membros = db.relationship('GrupoMembro', backref='grupo',
                                  cascade='all, delete-orphan', lazy='dynamic')
    mensagens = db.relationship('Mensagem', backref='grupo',
                                  cascade='all, delete-orphan', lazy='dynamic')


class GrupoMembro(db.Model):
    __tablename__ = 'grupo_membros'
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupos_chat.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    eh_admin = db.Column(db.Boolean, default=False)
    favorito = db.Column(db.Boolean, default=False)
    ultima_atividade = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    entrou_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario = db.relationship('Usuario')


class Mensagem(db.Model):
    __tablename__ = 'mensagens'
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupos_chat.id'), nullable=False)
    remetente_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    conteudo = db.Column(db.Text, nullable=True)
    imagem_path = db.Column(db.String(200), nullable=True)
    tipo = db.Column(db.String(20), default='texto')
    enviado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    deletado = db.Column(db.Boolean, default=False)


# ══════════════════════════════════════════════════════
#  PREMIUM / ASSINATURAS
# ══════════════════════════════════════════════════════

class Assinatura(db.Model):
    __tablename__ = 'assinaturas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    plano = db.Column(db.String(20), nullable=False)
    ciclo = db.Column(db.String(10), nullable=False)
    gateway_ref = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='ativa')
    inicio = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expira = db.Column(db.DateTime, nullable=True)
    renovacao_auto = db.Column(db.Boolean, default=True)


# ══════════════════════════════════════════════════════
#  SEGURANÇA
# ══════════════════════════════════════════════════════

class LogAuditoria(db.Model):
    __tablename__ = 'log_auditoria'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    acao = db.Column(db.String(100), nullable=False)
    detalhe = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(300), nullable=True)
    resultado = db.Column(db.String(20), default='ok')
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class ConteudoBloqueado(db.Model):
    __tablename__ = 'conteudo_bloqueado'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    tipo = db.Column(db.String(50), nullable=False)
    referencia = db.Column(db.String(200), nullable=True)
    motivo = db.Column(db.String(200), nullable=True)
    resolvido = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════
#  TOKEN DE RECUPERAÇÃO DE SENHA
# ══════════════════════════════════════════════════════

class TokenRecuperacao(db.Model):
    __tablename__ = 'tokens_recuperacao'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    token = db.Column(db.String(200), unique=True, nullable=False)
    expira = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario = db.relationship('Usuario')

    @property
    def valido(self):
        return not self.usado and datetime.now(timezone.utc) < _aware_utc(self.expira)


# ══════════════════════════════════════════════════════
#  ADS — CRÉDITOS POR ANÚNCIO
# ══════════════════════════════════════════════════════

class AdsCredit(db.Model):
    """Registra quando usuário free ganhou questões extras assistindo ads."""
    __tablename__ = 'ads_credits'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    tipo = db.Column(db.String(20), default='video') # 'video' / 'banner'
    questoes_extras = db.Column(db.Integer, default=2)
    usado = db.Column(db.Integer, default=0) # quantas já usadas
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expira_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc)+timedelta(hours=24))
    usuario = db.relationship('Usuario', backref='ads_credits')

    @property
    def disponivel(self):
        return self.usado < self.questoes_extras and datetime.now(timezone.utc) < _aware_utc(self.expira_em)


# ══════════════════════════════════════════════════════
#  TORNEIOS / COMPETIÇÕES
# ══════════════════════════════════════════════════════

# Configurações fixas por tipo de torneio
TORNEIO_CONFIG = {
    'micro':   {'questoes': 5,  'tempo_min': 10,  'label': 'Micro',   'icone': '\U000026A1'},
    'pequeno': {'questoes': 10, 'tempo_min': 20,  'label': 'Pequeno', 'icone': '\U0001F3AF'},
    'medio':   {'questoes': 20, 'tempo_min': 40,  'label': 'Médio',   'icone': '\U0001F3C5'},
    'grande':  {'questoes': 35, 'tempo_min': 70,  'label': 'Grande',  'icone': '\U0001F3C6'},
    'mega':    {'questoes': 50, 'tempo_min': 100, 'label': 'Mega',    'icone': '\U0001F451'},
}


class Torneio(db.Model):
    __tablename__ = 'torneios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    tipo = db.Column(db.String(20), default='pequeno')
    # Filtros — múltiplas matérias/dificuldades armazenadas como JSON string
    materias_json = db.Column(db.Text, default='[]') # ex: "[1,2,3]"
    dificuldades_json = db.Column(db.Text, default='[]') # ex: '["medio","dificil"]'
    num_questoes = db.Column(db.Integer, default=10)
    tempo_minutos = db.Column(db.Integer, default=20)
    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='aberto')
    recompensa_xp_1 = db.Column(db.Integer, default=500)
    recompensa_xp_2 = db.Column(db.Integer, default=300)
    recompensa_xp_3 = db.Column(db.Integer, default=150)
    recompensa_moedas_1 = db.Column(db.Integer, default=200)
    recompensa_moedas_2 = db.Column(db.Integer, default=100)
    recompensa_moedas_3 = db.Column(db.Integer, default=50)
    badge_temp = db.Column(db.String(50), nullable=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    participantes = db.relationship('TorneioParticipante', backref='torneio',
                                   cascade='all, delete-orphan', lazy='dynamic')

    @property
    def config(self):
        return TORNEIO_CONFIG.get(self.tipo, TORNEIO_CONFIG['pequeno'])

    @property
    def materias_ids(self):
        import json
        try: return json.loads(self.materias_json or '[]')
        except: return []

    @property
    def dificuldades_list(self):
        import json
        try: return json.loads(self.dificuldades_json or '[]')
        except: return []


class TorneioParticipante(db.Model):
    __tablename__ = 'torneio_participantes'
    id = db.Column(db.Integer, primary_key=True)
    torneio_id = db.Column(db.Integer, db.ForeignKey('torneios.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    pontuacao = db.Column(db.Integer, default=0)
    acertos = db.Column(db.Integer, default=0)
    respondidas = db.Column(db.Integer, default=0)
    finalizado = db.Column(db.Boolean, default=False)
    posicao = db.Column(db.Integer, nullable=True)
    recompensa_paga = db.Column(db.Boolean, default=False)
    entrou_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario = db.relationship('Usuario', backref='participacoes')


class TorneioResposta(db.Model):
    __tablename__ = 'torneio_respostas'
    id = db.Column(db.Integer, primary_key=True)
    torneio_id = db.Column(db.Integer, db.ForeignKey('torneios.id'), nullable=False)
    participante_id = db.Column(db.Integer, db.ForeignKey('torneio_participantes.id'), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey('questoes.id'), nullable=False)
    alternativa_id = db.Column(db.Integer, db.ForeignKey('alternativas.id'), nullable=True)
    resposta_texto = db.Column(db.Text, nullable=True)
    acertou = db.Column(db.Boolean, nullable=False)
    respondido_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    torneio = db.relationship('Torneio')
    participante = db.relationship('TorneioParticipante', backref='respostas')


# ══════════════════════════════════════════════════════
#  OFERTA TRIAL (1 mês grátis após 1 mês de uso)
# ══════════════════════════════════════════════════════

class OfertaTrial(db.Model):
    __tablename__ = 'ofertas_trial'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    ofertado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    aceito = db.Column(db.Boolean, default=False)
    aceito_em = db.Column(db.DateTime, nullable=True)
    usuario = db.relationship('Usuario', backref='ofertas_trial')


# ══════════════════════════════════════════════════════
#  PACOTES DE MOEDAS (compra real)
# ══════════════════════════════════════════════════════

class CompraMoedas(db.Model):
    """Registra compras de pacotes de moedas com dinheiro real."""
    __tablename__ = 'compras_moedas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    pacote_id = db.Column(db.String(30), nullable=False)
    moedas_base = db.Column(db.Integer, nullable=False)
    moedas_bonus = db.Column(db.Integer, default=0)
    valor_brl = db.Column(db.Float, nullable=False)
    gateway_ref = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='pendente') # pendente/pago/cancelado
    eh_primeira = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario = db.relationship('Usuario', backref='compras_moedas')


# ══════════════════════════════════════════════════════
#  CONFIGURAÇÕES DE GRUPO
# ══════════════════════════════════════════════════════

class GrupoConfig(db.Model):
    __tablename__ = 'grupo_configs'
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupos_chat.id'), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=True)
    icone = db.Column(db.String(50), default='\U0001F4AC')
    grupo = db.relationship('GrupoChat', backref=db.backref('config', uselist=False))


# ══════════════════════════════════════════════════════
#  QUESTÕES JÁ RESPONDIDAS (para não repetir em sessão)
# ══════════════════════════════════════════════════════

class QuestaoRespondidaSessao(db.Model):
    """Rastreia questões respondidas na sessão atual (simulado/questões avulsas)."""
    __tablename__ = 'questoes_respondidas_sessao'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    questao_id = db.Column(db.Integer, db.ForeignKey('questoes.id'), nullable=False)
    sessao_id = db.Column(db.String(64), nullable=False)  # UUID da sessão
    respondida_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════
#  RECOMPENSAS DE NÍVEL
# ══════════════════════════════════════════════════════

RECOMPENSAS_NIVEL = {
    5:   {'moedas': 30,  'badge': None,               'borda': None},
    10:  {'moedas': 80,  'badge': None,               'borda': None},
    20:  {'moedas': 150, 'badge': 'badge-veterano',   'borda': None},
    30:  {'moedas': 200, 'badge': None,               'borda': None},
    50:  {'moedas': 400, 'badge': 'badge-mestre',     'borda': 'border-dourada'},
    75:  {'moedas': 600, 'badge': None,               'borda': 'border-galaxia'},
    100: {'moedas': 1000,'badge': 'badge-lenda',      'borda': 'border-rainbow'},
}


class RecompensaNivelConcedida(db.Model):
    __tablename__ = 'recompensas_nivel'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    nivel = db.Column(db.Integer, nullable=False)
    concedida_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════
#  HISTÓRICO DE PAGAMENTOS
# ══════════════════════════════════════════════════════

class PagamentoHistorico(db.Model):
    __tablename__ = 'pagamento_historico'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    plano = db.Column(db.String(20), nullable=False)# basic/inter/advan
    ciclo = db.Column(db.String(10), nullable=False) # mensal/anual
    valor = db.Column(db.Float,  nullable=False)
    status = db.Column(db.String(20), default='pago') # pago/cancelado/pendente
    # Dados do cartão (censurados)
    cartao_final = db.Column(db.String(4), nullable=True) # últimos 4 dígitos
    cartao_nome = db.Column(db.String(100), nullable=True) # nome do titular
    cartao_numero = db.Column(db.String(25), nullable=True) # formato: **** **** **** 1234
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    descricao = db.Column(db.String(200), nullable=True)

    usuario = db.relationship('Usuario', backref='pagamentos')