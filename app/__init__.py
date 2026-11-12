import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
# pyrefly: ignore [missing-import]
from flask_mail import Mail
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
mail = Mail()


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # ── Configurações ────────────────────────────────
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        os.getenv('DATABASE_URL') or
        'sqlite:///' + os.path.join(app.instance_path, 'database.db')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False  # Set True in production with HTTPS
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
    app.config['WTF_CSRF_TIME_LIMIT'] = 7200   # 2 hours
    app.config['BCRYPT_LOG_ROUNDS'] = 13     # strong but not too slow

    # ── Email ────────────────────────────────────────
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME', 'noreply@exquest.com')

    os.makedirs(app.instance_path, exist_ok=True)

    # ── Extensões ────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

    # ── Security headers ─────────────────────────────
    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        # CSP — allows CDN for KaTeX / Tailwind etc.
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self'; "
            "frame-src 'none'; "
            "object-src 'none';"
        )
        # Only set CSP on HTML responses to avoid breaking assets
        if 'text/html' in response.content_type:
            response.headers['Content-Security-Policy'] = csp
        return response

    # ── Blueprints ───────────────────────────────────
    from app.views import main
    app.register_blueprint(main)

    # ── Context processor ─────────────────────────────
    @app.context_processor
    def inject_globals():
        from flask_wtf.csrf import generate_csrf
        from markupsafe import Markup

        AVATARES = {
            'avatar_1':'\U0001F989','avatar_2':'\U0001F680','avatar_3':'\U00002B50','avatar_4':'\U0001F48E',
            'avatar_5':'\U000026A1','avatar_6':'\U0001F525','avatar_7':'\U0001F52E','avatar_8':'\U0001F6E1\U0000FE0F',
        }

        def csrf_token_field():
            token = generate_csrf()
            return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')

        def avatar_display(usuario):
            if usuario.icon_path:
                url = '/static/data/icon/' + usuario.icon_path
                return Markup('<img src="' + url + '" alt="avatar" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;">')
            emoji_key = usuario.icon_emoji or 'avatar_1'
            if emoji_key and emoji_key != 'avatar_1':
                return Markup(AVATARES.get(emoji_key, ''))
            return Markup('<img src="/static/img/foto_perfil_padrao.png" alt="avatar" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;" onerror="this.src=\'/static/img/foto_perfil_padrao.svg\'">')

        def banner_url(usuario):
            if usuario.banner_path:
                return f'/static/data/banner/{usuario.banner_path}'
            return None

        def nick_html(usuario, extra_style=''):
            """Renderiza o nick com cor/gradiente/fonte do premium."""
            style = usuario.nick_style + extra_style
            font = usuario.nick_font_family
            if font:
                style += f'font-family:{font};'
            name = Markup.escape(usuario.nome_completo)
            return Markup(f'<span style="{style}">{name}</span>')

        return dict(
            avatares=AVATARES,
            csrf_token_field=csrf_token_field,
            avatar_display=avatar_display,
            banner_url=banner_url,
            nick_html=nick_html,
        )

    # ── Criar tabelas e seed ─────────────────────────
    with app.app_context():
        db.create_all()
        # Add new columns if they don't exist (safe for SQLite & Postgres)
        _safe_add_columns()
        _seed_loja_inicial()

    return app


def _safe_add_columns():
    """Add new columns without breaking existing DBs."""
    from sqlalchemy import text, inspect as _inspect
    try:
        engine = db.engine
        inspector = _inspect(engine)
        cols = {c['name'] for c in inspector.get_columns('usuario')}
        new_cols = {
            'bloquear_pedidos_amizade': 'BOOLEAN DEFAULT FALSE',
            'premium_ciclo': 'VARCHAR(10)',
            'premium_cancelar_em': 'DATETIME',
        }
        with engine.connect() as conn:
            for col, definition in new_cols.items():
                if col not in cols:
                    conn.execute(text(f'ALTER TABLE usuario ADD COLUMN {col} {definition}'))
            conn.commit()
    except Exception:
        pass  # Table may not exist yet on first run


def _seed_loja_inicial():
    from app.models import ItemLoja
    if ItemLoja.query.count() > 0:
        return
    itens = [
        # ── BORDAS (todas via CSS puro — sem imagens externas) ──
        dict(nome='Borda Prata',       descricao='Anel prateado suave ao redor do avatar.',
             tipo='borda', raridade='comum',    preco=80,   css_class='border-prata'),
        dict(nome='Borda Ouro',        descricao='Anel dourado clássico.',
             tipo='borda', raridade='raro',     preco=200,  css_class='border-dourada'),
        dict(nome='Borda Neon Roxo',   descricao='Borda neon roxa com brilho pulsante.',
             tipo='borda', raridade='epico',    preco=500,  css_class='border-neon-roxo'),
        dict(nome='Borda Neon Azul',   descricao='Borda neon azul elétrico vibrante.',
             tipo='borda', raridade='epico',    preco=550,  css_class='border-neon-azul'),
        dict(nome='Borda Chamas',      descricao='Animação de chamas laranja ao redor.',
             tipo='borda', raridade='epico',    preco=750,  css_class='border-chamas'),
        dict(nome='Borda Gelo',        descricao='Cristais de gelo azuis girando lentamente.',
             tipo='borda', raridade='epico',    preco=800,  css_class='border-gelo'),
        dict(nome='Borda Galáxia',     descricao='Conic-gradient girando com efeito galáxia.',
             tipo='borda', raridade='lendario', preco=2000, css_class='border-galaxia'),
        dict(nome='Borda Arco-Íris',   descricao='Arco-íris animado girando continuamente.',
             tipo='borda', raridade='lendario', preco=2500, css_class='border-rainbow'),
        dict(nome='Borda Plasma',      descricao='Plasma bicolor com pulso elétrico roxo/rosa.',
             tipo='borda', raridade='lendario', preco=3000, css_class='border-plasma'),
        dict(nome='Borda Dourada Rara',descricao='Dupla camada dourada com shimmer animado.',
             tipo='borda', raridade='lendario', preco=3500, css_class='border-gold-rare'),

        # ── EFEITOS DE PERFIL (via CSS + JS canvas) ──
        dict(nome='Efeito Aurora',       descricao='Aurora boreal suave animada no fundo do perfil.',
             tipo='efeito', raridade='raro',    preco=300,  css_class='efeito-aurora'),
        dict(nome='Efeito Cosmos',       descricao='Campo de estrelas cintilantes ao fundo.',
             tipo='efeito', raridade='epico',   preco=600,  css_class='efeito-cosmos'),
        dict(nome='Efeito Matrix',       descricao='Chuva de código verde sobre o perfil.',
             tipo='efeito', raridade='epico',   preco=800,  css_class='efeito-matrix'),
        dict(nome='Partículas Douradas', descricao='Partículas douradas flutuantes interativas com o cursor.',
             tipo='efeito', raridade='lendario',preco=1800, css_class='efeito-particles-gold'),
        dict(nome='Partículas Roxas',    descricao='Partículas roxas/lilás interativas com o cursor.',
             tipo='efeito', raridade='lendario',preco=1800, css_class='efeito-particles-purple'),
        dict(nome='Partículas Azuis',    descricao='Partículas azul neon interativas com o cursor.',
             tipo='efeito', raridade='lendario',preco=1800, css_class='efeito-particles-blue'),
        dict(nome='Efeito Fogo',         descricao='Chamas animadas subindo pelo perfil.',
             tipo='efeito', raridade='lendario',preco=2200, css_class='efeito-fogo'),
        dict(nome='Efeito Trovão',       descricao='Raios elétricos azuis cruzando o perfil.',
             tipo='efeito', raridade='lendario',preco=2200, css_class='efeito-trovao'),
        dict(nome='Efeito Chuva',        descricao='Gotas de chuva animadas no perfil.',
             tipo='efeito', raridade='epico',   preco=900,  css_class='efeito-chuva'),
        dict(nome='Efeito Bokeh',        descricao='Bolinhas de luz desfocadas flutuando suavemente.',
             tipo='efeito', raridade='raro',    preco=400,  css_class='efeito-bokeh'),

        # ── BADGES ──
        dict(nome='Badge Estudante',  descricao='Para quem está começando a jornada.',
             tipo='badge', raridade='comum',    preco=50,   css_class='badge-estudante'),
        dict(nome='Badge Veterano',   descricao='Badge de veterano da plataforma.',
             tipo='badge', raridade='raro',     preco=400,  css_class='badge-veterano'),
        dict(nome='Badge Mestre',     descricao='Badge de mestre com brilho especial.',
             tipo='badge', raridade='epico',    preco=1200, css_class='badge-mestre'),
        dict(nome='Badge Lenda',      descricao='Badge lendária com partículas animadas.',
             tipo='badge', raridade='lendario', preco=4000, css_class='badge-lenda'),

        # ── BOOSTS ──
        dict(nome='Boost XP +50% (24h)',    descricao='Aumenta ganho de XP em 50% por 24h.',
             tipo='boost_xp',    raridade='comum', preco=120, valor_boost=50,  duracao_h=24),
        dict(nome='Boost XP +100% (48h)',   descricao='Dobra o ganho de XP por 48h.',
             tipo='boost_xp',    raridade='raro',  preco=350, valor_boost=100, duracao_h=48),
        dict(nome='Boost Moedas +50% (24h)',descricao='Aumenta ganho de moedas em 50% por 24h.',
             tipo='boost_moeda', raridade='comum', preco=100, valor_boost=50,  duracao_h=24),
        dict(nome='Boost Moedas +100% (48h)',descricao='Dobra o ganho de moedas por 48h.',
             tipo='boost_moeda', raridade='raro',  preco=300, valor_boost=100, duracao_h=48),

        # ── POWER-UPS ──
        dict(nome='Escudo de Streak',    descricao='Protege sua streak por 1 dia de inatividade.',
             tipo='streak_shield', raridade='raro',  preco=180, valor_boost=1),
        dict(nome='Escudo Duplo',        descricao='Protege sua streak por 2 dias seguidos.',
             tipo='streak_shield', raridade='epico', preco=400, valor_boost=2),
    ]
    from app import db
    for d in itens:
        db.session.add(ItemLoja(**d))
    db.session.commit()
