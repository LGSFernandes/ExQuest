import pytest
from flask import g

from app import create_app
from app.extensions import db


@pytest.fixture(autouse=True)
def _limpa_estado_global():
    from app import cache
    from app.extensions import outbox
    outbox.clear()
    cache.limpar_tudo_memoria()
    yield


@pytest.fixture()
def app():
    app = create_app("testing")
    # o app context do teste é compartilhado entre clientes: sem isto, o usuário do 1º cliente vazaria para o 2º via g
    app.before_request(lambda: g.pop("_login_user", None) and None)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_logado(client):
    from app.extensions import db
    from app.models import Usuario
    from tests.test_auth import DADOS, registrar
    registrar(client)
    u = Usuario.query.filter_by(email=DADOS["email"]).one()
    u.is_admin = True
    db.session.commit()
    return client
