from app.extensions import db
from app.models import Notificacao, Usuario
from app.services import notificacoes as svc
from tests.test_auth import DADOS, registrar


def _eu(client):
    registrar(client)
    return Usuario.query.filter_by(email=DADOS["email"]).one()


def test_sino_contador_lista_e_marcar_lidas(client):
    u = _eu(client)
    assert "sino-num" not in client.get("/").data.decode()
    svc.criar(u.id, "teste", "Olá", "corpo", "/ranking/"); svc.criar(u.id, "teste", "Dois")
    db.session.commit()
    assert svc.nao_lidas(u.id) == 2 and 'sino-num' in client.get("/").data.decode()
    assert "Olá" in client.get("/notificacoes/").data.decode()
    r = client.get(f"/notificacoes/{Notificacao.query.first().id}/abrir")
    assert r.status_code == 302 and r.headers["Location"].endswith("/ranking/") and svc.nao_lidas(u.id) == 1
    client.post("/notificacoes/lidas")
    assert svc.nao_lidas(u.id) == 0


def test_nao_abre_notificacao_alheia_e_ignora_url_externa(client):
    u = _eu(client)
    outro = Usuario(username="o", email="o@x.com", nome="O", sobrenome="X", tag="0009", senha_hash="x")
    db.session.add(outro); db.session.flush()
    svc.criar(outro.id, "t", "Do outro", None, "/x")
    svc.criar(u.id, "t", "Phishing", None, "https://evil.example/")
    svc.criar(u.id, "t", "Phishing2", None, "//evil.example/")
    db.session.commit()
    alheia = Notificacao.query.filter_by(usuario_id=outro.id).one()
    assert client.get(f"/notificacoes/{alheia.id}/abrir").status_code == 404
    assert Notificacao.query.get(alheia.id).lida is False
    for n in Notificacao.query.filter_by(usuario_id=u.id):
        assert n.url is None
        assert client.get(f"/notificacoes/{n.id}/abrir").headers["Location"].endswith("/notificacoes/")


def test_poda_mantem_so_as_ultimas(client):
    u = _eu(client)
    for i in range(svc.LIMITE_POR_USUARIO + 5):
        svc.criar(u.id, "t", f"n{i}")
    db.session.commit(); svc.podar(u.id); db.session.commit()
    assert Notificacao.query.filter_by(usuario_id=u.id).count() == svc.LIMITE_POR_USUARIO
