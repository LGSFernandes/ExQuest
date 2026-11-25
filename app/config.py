"""Configuração por ambiente. Nada aqui tem credencial: tudo vem de variáveis de ambiente (.env)."""
from datetime import timedelta
import logging
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_SECRETS_FRACOS = {"", "dev-secret", "changeme", "change-me", "secret", "troque-esta-chave"}
log = logging.getLogger(__name__)


def _bool(nome: str, padrao: bool = False) -> bool:
    v = os.getenv(nome)
    return padrao if v is None else v.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, padrao))
    except (TypeError, ValueError):
        return padrao


def _db_uri() -> str:
    uri = os.getenv("DATABASE_URL", "").strip()
    if uri.startswith("postgres://"):
        uri = "postgresql+psycopg://" + uri[len("postgres://"):]
    elif uri.startswith("postgresql://"):
        uri = "postgresql+psycopg://" + uri[len("postgresql://"):]
    # sem URL: SQLite em instance/database.db (caminho relativo resolvido pelo Flask-SQLAlchemy)
    return uri or "sqlite:///database.db"


class Config:
    APP_ENV = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").lower()
    TESTING = False
    DEBUG = False
    BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    SITE_NAME = "ExQuest"

    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}  # ajustado por engine_options() conforme o banco
    SQLITE_WAL = _bool("SQLITE_WAL", True)

    MAX_CONTENT_LENGTH = 12 * 1024 * 1024  # teto de qualquer requisição; limites por tipo ficam em services/uploads
    WTF_CSRF_TIME_LIMIT = 7200
    BCRYPT_LOG_ROUNDS = _int("BCRYPT_LOG_ROUNDS", 12)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 14

    # Proxy reverso: quantos proxies confiáveis estão na frente (Nginx/Caddy = 1). 0 = nenhum.
    TRUSTED_PROXIES = _int("TRUSTED_PROXIES", 0)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # Uploads públicos (avatar, banner, imagem de questão) e anexos de chat (privados).
    UPLOAD_ROOT = os.getenv("UPLOAD_ROOT") or str(BASE_DIR / "app" / "static" / "data")

    # E-mail
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    CONTATO_EMAIL = os.getenv("CONTATO_EMAIL", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER") or os.getenv("MAIL_USERNAME") or "noreply@exquest.local"

    # Integrações (todas opcionais; o recurso correspondente informa "indisponível" quando ausente)
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")
    MP_SANDBOX = _bool("MP_SANDBOX", False)
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # Desempenho -------------------------------------------------------------------------------
    # Pool de conexões (só vale para PostgreSQL/MySQL; o SQLite local usa conexão por arquivo).
    DB_POOL_SIZE = _int("DB_POOL_SIZE", 10)
    DB_MAX_OVERFLOW = _int("DB_MAX_OVERFLOW", 20)
    DB_POOL_TIMEOUT = _int("DB_POOL_TIMEOUT", 10)
    DB_POOL_RECYCLE = _int("DB_POOL_RECYCLE", 1800)
    DB_CONNECT_TIMEOUT = _int("DB_CONNECT_TIMEOUT", 5)
    DB_STATEMENT_TIMEOUT_MS = _int("DB_STATEMENT_TIMEOUT_MS", 15000)
    # Timeouts de APIs externas (segundos): conexão e leitura separados
    HTTP_CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", "3.05"))
    HTTP_READ_TIMEOUT = float(os.getenv("HTTP_READ_TIMEOUT", "10"))
    SMTP_TIMEOUT = _int("SMTP_TIMEOUT", 10)
    # Cache (Redis opcional; sem REDIS_URL usa memória do processo, válida para 1 instância)
    REDIS_URL = os.getenv("REDIS_URL", "").strip()
    CACHE_PREFIXO = os.getenv("CACHE_PREFIXO", "exq")
    # Fila de tarefas: "eager" executa na hora (padrão, sem worker); "queue" grava em `jobs` e o worker executa
    JOBS_MODE = os.getenv("JOBS_MODE", "eager").lower()
    MANUTENCAO_INLINE = _bool("MANUTENCAO_INLINE", True)
    # CDN: URL base que serve /static (ex.: https://cdn.exemplo.com). Vazio = mesmo domínio.
    CDN_URL = os.getenv("CDN_URL", "").strip().rstrip("/")
    COMPRESS_HTML = _bool("COMPRESS_HTML", True)
    # Observabilidade
    SLOW_REQUEST_MS = _int("SLOW_REQUEST_MS", 800)
    RUM_ENABLED = _bool("RUM_ENABLED", True)
    RUM_SAMPLE = float(os.getenv("RUM_SAMPLE", "1.0"))  # 0..1: fração de visitas que reporta métricas
    RUM_RETENCAO_DIAS = _int("RUM_RETENCAO_DIAS", 30)
    OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "exquest")
    OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    OTEL_ENABLED = _bool("OTEL_ENABLED", False)  # também exige OTEL_EXPORTER_OTLP_ENDPOINT e requirements-otel.txt

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_JSON = _bool("LOG_JSON", False)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @classmethod
    def resolve_secret_key(cls, config: "Config") -> str:
        chave = os.getenv("SECRET_KEY", "").strip()
        if config.APP_ENV == "production":
            if chave.lower() in _SECRETS_FRACOS or len(chave) < 32:
                raise RuntimeError(
                    "SECRET_KEY ausente ou fraca em produção. Gere uma com: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
            return chave
        if chave.lower() in _SECRETS_FRACOS:
            log.warning("SECRET_KEY ausente/fraca: usando chave efêmera (sessões caem a cada reinício).")
            return secrets.token_urlsafe(48)
        return chave


def engine_options(uri: str, cfg) -> dict:
    """Opções do engine SQLAlchemy por banco. SQLite: sem pool dimensionado (arquivo local). Outros: pool, reciclagem e timeouts."""
    opcoes: dict = {"pool_pre_ping": True}
    if uri.startswith("sqlite"):
        return opcoes
    opcoes.update(pool_size=cfg.DB_POOL_SIZE, max_overflow=cfg.DB_MAX_OVERFLOW, pool_timeout=cfg.DB_POOL_TIMEOUT,
                  pool_recycle=cfg.DB_POOL_RECYCLE)
    if uri.startswith("postgresql"):
        opcoes["connect_args"] = {"connect_timeout": cfg.DB_CONNECT_TIMEOUT,
                                  "options": f"-c statement_timeout={cfg.DB_STATEMENT_TIMEOUT_MS}"}
    return opcoes


class DevelopmentConfig(Config):
    DEBUG = False  # nunca liga o depurador Werkzeug por padrão; use FLASK_DEBUG=1 conscientemente


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SEND_FILE_MAX_AGE_DEFAULT = 86400  # sem versão na URL: 1 dia; com ?v=hash o cabeçalho passa a 1 ano (app/assets.py)


class TestingConfig(Config):
    TESTING = True
    APP_ENV = "testing"
    WTF_CSRF_ENABLED = False
    BCRYPT_LOG_ROUNDS = 4
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    RATELIMIT_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    JOBS_MODE = "eager"
    SERVER_NAME = None


def pick(nome: str | None = None) -> Config:
    nome = (nome or os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").lower()
    return {"production": ProductionConfig, "testing": TestingConfig}.get(nome, DevelopmentConfig)()
