"""Corridas reais: várias threads, SQLite em arquivo (cada thread tem sua própria sessão/conexão)."""
import threading

import pytest

from app import create_app
from app.extensions import db
from app.models import Usuario
from app.services import limits, wallet


@pytest.fixture()
def app_arquivo(tmp_path):
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'c.db'}"})
    with app.app_context():
        db.create_all()
        u = Usuario(nome="A", sobrenome="B", username="ana", email="a@x.com", tag="AAAA", moedas=0)
        db.session.add(u)
        db.session.flush()
        wallet.creditar(u.id, 100, "saldo_inicial", "saldo_inicial:1")
        db.session.commit()
        uid = u.id
    yield app, uid
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _rodar(app, n, alvo):
    resultados, barreira = [], threading.Barrier(n)

    def w(i):
        with app.app_context():
            barreira.wait()
            try:
                resultados.append(alvo(i))
                db.session.commit()
            except Exception as e:  # noqa: BLE001
                db.session.rollback()
                resultados.append(e)
            finally:
                db.session.remove()

    ts = [threading.Thread(target=w, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return resultados


def test_debitos_simultaneos_nunca_deixam_saldo_negativo(app_arquivo):
    app, uid = app_arquivo
    res = _rodar(app, 8, lambda i: wallet.debitar(uid, 30, "compra_item", f"compra:{i}"))
    ok = [r for r in res if not isinstance(r, Exception)]
    falhas = [r for r in res if isinstance(r, wallet.SaldoInsuficiente)]
    outros = [r for r in res if isinstance(r, Exception) and not isinstance(r, wallet.SaldoInsuficiente)]
    assert not outros, outros
    assert len(ok) == 3 and len(falhas) == 5  # 100 // 30
    with app.app_context():
        assert wallet.conferir(uid) == (True, 10, 10)


def test_mesma_chave_em_paralelo_credita_uma_vez(app_arquivo):
    app, uid = app_arquivo
    res = _rodar(app, 8, lambda i: wallet.creditar(uid, 50, "compra_moedas", "pagamento:42"))
    assert not [r for r in res if isinstance(r, Exception)], res
    assert sum(1 for r in res if r.novo) == 1
    with app.app_context():
        assert wallet.conferir(uid) == (True, 150, 150)


def test_limite_diario_vale_sob_concorrencia(app_arquivo):
    app, uid = app_arquivo

    def consumir(_):
        u = db.session.get(Usuario, uid)
        return limits.consumir_questao(u)

    res = _rodar(app, 10, consumir)
    assert not [r for r in res if isinstance(r, Exception)], res
    assert sum(1 for r in res if r is True) == 3  # plano gratuito: 3 por dia
