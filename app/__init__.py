"""ExQuest — fábrica da aplicação (application factory)."""
import os

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app import config as cfg
from app.extensions import bcrypt, csrf, db, limiter, login_manager, migrate, oauth

load_dotenv()


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    # `.env` é lido antes de escolher o ambiente (APP_ENV pode estar nele)
    config = cfg.pick(config_name)
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config)
    app.config["SECRET_KEY"] = cfg.Config.resolve_secret_key(config)
    app.config["IS_PRODUCTION"] = config.is_production
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = cfg.engine_options(app.config["SQLALCHEMY_DATABASE_URI"], config)
    app.config.update(overrides or {})  # usado por testes
    os.makedirs(app.instance_path, exist_ok=True)

    if app.config["TRUSTED_PROXIES"]:
        n = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    if not app.config["TESTING"]:  # em testes o pytest controla o logging
        from app.logging_setup import configure_logging
        configure_logging(app)

    db.init_app(app)
    # render_as_batch: necessário para ALTER TABLE no SQLite; compare_type: detecta mudança de tipo no autogenerate
    migrate.init_app(app, db, render_as_batch=True, compare_type=True)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    oauth.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Entre na sua conta para acessar esta página."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    from app import models  # noqa: F401  (registra todas as tabelas em db.metadata)
    from app.db_setup import install_sqlite_pragmas
    install_sqlite_pragmas(app)

    from app import assets, telemetry
    assets.init_app(app)
    telemetry.init_app(app)

    from app.hooks import register_hooks
    register_hooks(app)

    from app.cli import register_cli
    register_cli(app)

    from app.blueprints import register_blueprints
    register_blueprints(app)

    return app
