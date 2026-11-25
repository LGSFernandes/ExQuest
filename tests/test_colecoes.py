from app.extensions import db
from app.models import Colecao, ColecaoItem, Materia, Questao, Usuario
from tests.test_auth import DADOS, registrar


def _setup(client):
    registrar(client)
    m = Materia(nome="M"); db.session.add(m); db.session.flush()
    q = Questao(materia_id=m.id, enunciado="Q1", tipo="discursiva", dificuldade="facil", ativo=True)
    db.session.add(q); db.session.commit()
    return q


def test_favoritos_criados_sob_demanda_e_toggle_idempotente(client):
    q = _setup(client)
    assert client.get("/colecoes/").status_code == 200
    fav = Colecao.query.filter_by(eh_favoritos=True).one()
    for presente, esperado in ((True, 1), (True, 1), (False, 0), (False, 0)):  # repetir não duplica nem falha
        r = client.post(f"/colecoes/api/questao/{q.id}", json={"colecao_id": fav.id, "presente": presente})
        assert r.status_code == 200 and ColecaoItem.query.count() == esperado


def test_nao_mexe_em_colecao_de_outro_usuario_nem_dados_invalidos(client):
    q = _setup(client)
    outro = Usuario(username="o", email="o@x.com", nome="O", sobrenome="X", tag="0009", senha_hash="x")
    db.session.add(outro); db.session.flush()
    alheia = Colecao(usuario_id=outro.id, nome="Dele"); db.session.add(alheia); db.session.commit()
    assert client.post(f"/colecoes/api/questao/{q.id}", json={"colecao_id": alheia.id, "presente": True}).status_code == 400
    assert client.post(f"/colecoes/api/questao/{q.id}", json={"colecao_id": "1", "presente": True}).status_code == 400
    assert client.post(f"/colecoes/api/questao/99999", json={"colecao_id": alheia.id, "presente": True}).status_code == 400
    assert ColecaoItem.query.count() == 0
    assert client.get(f"/colecoes/{alheia.id}").status_code == 404
    assert client.post(f"/colecoes/{alheia.id}/excluir").status_code == 404
    assert Colecao.query.filter_by(id=alheia.id).count() == 1


def test_criar_excluir_e_praticar_colecao(client):
    q = _setup(client)
    assert client.post("/colecoes/nova", data={"nome": "  Revisar   depois "}).status_code == 302
    c = Colecao.query.filter_by(eh_favoritos=False).one()
    assert c.nome == "Revisar depois"
    client.post("/colecoes/nova", data={"nome": "revisar DEPOIS"})  # duplicado, sem diferenciar caixa
    assert Colecao.query.filter_by(eh_favoritos=False).count() == 1
    client.post(f"/colecoes/api/questao/{q.id}", json={"colecao_id": c.id, "presente": True})
    assert "Q1" in client.get(f"/questoes/?colecao_id={c.id}").data.decode()   # pratica só o que está na coleção
    assert b"Salvar" in client.get(f"/questoes/?colecao_id={c.id}").data
    assert client.get("/questoes/?colecao_id=9999").status_code == 404
    client.post("/colecoes/")  # método não permitido, sem erro 500
    fav = Colecao.query.filter_by(eh_favoritos=True).one()
    client.post(f"/colecoes/{fav.id}/excluir")
    assert Colecao.query.filter_by(eh_favoritos=True).count() == 1             # Favoritos é protegida
    client.post(f"/colecoes/{c.id}/excluir")
    assert Colecao.query.filter_by(id=c.id).count() == 0 and Questao.query.count() == 1 and ColecaoItem.query.count() == 0


def test_plano_gratuito_limita_colecoes_sem_contar_favoritos(client):
    _setup(client)
    for i in range(5):
        client.post("/colecoes/nova", data={"nome": f"C{i}"})
    assert Colecao.query.filter_by(eh_favoritos=False).count() == 3   # plano gratuito: 3
    client.get("/colecoes/")
    assert Colecao.query.filter_by(eh_favoritos=True).count() == 1
