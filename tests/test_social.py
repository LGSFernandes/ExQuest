import io

from PIL import Image

from app.extensions import db
from app.models import Amizade, Denuncia, GrupoChat, Mensagem, Notificacao, Usuario
from app.services import amizades
from tests.test_auth import DADOS, registrar


def _duas_contas(app, client):
    registrar(client)
    c2 = app.test_client()
    registrar(c2, email="bia@exemplo.com", username="bia", nome="Bia")
    a = Usuario.query.filter_by(email=DADOS["email"]).one()
    b = Usuario.query.filter_by(email="bia@exemplo.com").one()
    return a, b, c2


def _id(u):
    return f"{u.username}#{u.tag}"


def _amigos(client, c2, a, b):
    client.post("/amigos/pedir", data={"alvo": _id(b)})
    c2.post(f"/amigos/{Amizade.query.one().id}/aceitar")


def test_pedido_aceite_notifica_e_respeita_regras(app, client):
    a, b, c2 = _duas_contas(app, client)
    client.post("/amigos/pedir", data={"alvo": "naoexiste#0000"})
    client.post("/amigos/pedir", data={"alvo": _id(a)})  # a si mesmo
    assert Amizade.query.count() == 0
    client.post("/amigos/pedir", data={"alvo": _id(b)})
    client.post("/amigos/pedir", data={"alvo": b.username})  # repetido: só um pedido
    assert Amizade.query.count() == 1 and Notificacao.query.filter_by(usuario_id=b.id, tipo="amizade").count() == 1
    r = Amizade.query.one()
    client.post(f"/amigos/{r.id}/aceitar")  # só o destinatário aceita
    assert Amizade.query.one().status == "pendente"
    c2.post(f"/amigos/{r.id}/aceitar")
    assert Amizade.query.one().status == "aceito" and amizades.sao_amigos(a.id, b.id)
    assert Notificacao.query.filter_by(usuario_id=a.id, tipo="amizade").count() == 1
    assert "Bia" in client.get("/amigos").data.decode()


def test_pedidos_cruzados_viram_amizade_e_recusa_nao_permite_insistir(app, client):
    a, b, c2 = _duas_contas(app, client)
    client.post("/amigos/pedir", data={"alvo": _id(b)})
    c2.post("/amigos/pedir", data={"alvo": _id(a)})  # o outro já tinha pedido: aceita direto
    assert Amizade.query.one().status == "aceito"
    db.session.delete(Amizade.query.one()); db.session.commit()
    client.post("/amigos/pedir", data={"alvo": _id(b)})
    c2.post(f"/amigos/{Amizade.query.one().id}/recusar")
    client.post("/amigos/pedir", data={"alvo": _id(b)})
    assert Amizade.query.one().status == "recusado"


def test_bloqueio_encerra_amizade_e_impede_pedido_e_conversa(app, client):
    a, b, c2 = _duas_contas(app, client)
    _amigos(client, c2, a, b)
    g = client.post(f"/mensagens/direta/{b.id}", follow_redirects=False)
    assert g.status_code == 302
    gid = GrupoChat.query.one().id
    client.post(f"/bloqueios/{b.id}")
    assert Amizade.query.count() == 0
    c2.post("/amigos/pedir", data={"alvo": _id(a)})
    assert Amizade.query.count() == 0
    r = c2.post(f"/mensagens/{gid}/enviar", data={"texto": "oi"})
    assert r.status_code == 400 and Mensagem.query.count() == 0
    client.post(f"/bloqueios/{b.id}/desfazer")
    assert amizades.bloqueado_entre(a.id, b.id) is False


def test_limite_de_amigos_do_plano_gratuito(app, client):
    a, b, c2 = _duas_contas(app, client)
    for i in range(15):
        u = Usuario(username=f"u{i}", email=f"u{i}@x.com", nome="U", sobrenome="X", tag=f"{i:04d}", senha_hash="x")
        db.session.add(u); db.session.flush()
        db.session.add(Amizade(solicitante_id=a.id, destinatario_id=u.id, status="aceito"))
    db.session.commit()
    client.post("/amigos/pedir", data={"alvo": _id(b)})
    assert Amizade.query.filter_by(destinatario_id=b.id).count() == 0   # a está no limite (15)


def test_chat_direto_so_entre_amigos_e_mensagens(app, client):
    a, b, c2 = _duas_contas(app, client)
    client.post(f"/mensagens/direta/{b.id}")  # ainda não são amigos
    assert GrupoChat.query.count() == 0
    _amigos(client, c2, a, b)
    client.post(f"/mensagens/direta/{b.id}"); client.post(f"/mensagens/direta/{b.id}")
    g = GrupoChat.query.one()  # reaproveita a conversa
    r = client.post(f"/mensagens/{g.id}/enviar", data={"texto": "<b>oi</b> $x^2$"})
    assert r.status_code == 200 and r.get_json()["mensagem"]["texto"] == "<b>oi</b> $x^2$"  # guardado como digitado
    pagina = c2.get(f"/mensagens/{g.id}").data.decode()
    assert "&lt;b&gt;oi&lt;/b&gt;" in pagina and "<b>oi</b>" not in pagina                  # exibido escapado
    assert client.post(f"/mensagens/{g.id}/enviar", data={"texto": "   "}).status_code == 400
    assert client.post(f"/mensagens/{g.id}/enviar", data={"texto": "x" * 2001}).status_code == 400  # recusa, não corta
    assert Mensagem.query.count() == 1
    novas = c2.get(f"/mensagens/{g.id}/novas?depois=0").get_json()["mensagens"]
    assert len(novas) == 1 and novas[0]["meu"] is False
    assert c2.get(f"/mensagens/{g.id}/novas?depois={novas[0]['id']}").get_json()["mensagens"] == []
    assert 'aria-label="1 não lidas"' not in c2.get("/mensagens").data.decode()  # c2 abriu a conversa: lida


def test_estranho_nao_ve_nem_envia_nem_baixa_imagem(app, client):
    a, b, c2 = _duas_contas(app, client)
    _amigos(client, c2, a, b)
    client.post(f"/mensagens/direta/{b.id}")
    g = GrupoChat.query.one()
    buf = io.BytesIO(); Image.new("RGB", (20, 20), "red").save(buf, "PNG")
    r = client.post(f"/mensagens/{g.id}/enviar", data={"texto": "foto", "imagem": (io.BytesIO(buf.getvalue()), "x.png")}, content_type="multipart/form-data")
    url = r.get_json()["mensagem"]["imagem"]
    assert c2.get(url).status_code == 200 and c2.get(url).headers["Cache-Control"] == "private, max-age=3600"
    est = app.test_client()
    registrar(est, email="eva@exemplo.com", username="eva", nome="Eva")
    for u in (f"/mensagens/{g.id}", f"/mensagens/{g.id}/novas", url):
        assert est.get(u).status_code == 404
    assert est.post(f"/mensagens/{g.id}/enviar", data={"texto": "oi"}).status_code == 404
    assert est.get("/static/data/chat/qualquer.png").status_code in (403, 404)
    # arquivo que não é imagem é recusado e nada é gravado
    r = client.post(f"/mensagens/{g.id}/enviar", data={"imagem": (io.BytesIO(b"<script>alert(1)</script>"), "a.png")}, content_type="multipart/form-data")
    assert r.status_code == 400 and Mensagem.query.count() == 1
    assert client.get(f"/mensagens/{g.id}/imagem/..%2F..%2Fapp.py").status_code == 404


def test_grupo_admin_adiciona_sai_e_denuncia(app, client):
    a, b, c2 = _duas_contas(app, client)
    _amigos(client, c2, a, b)
    r = client.post("/mensagens/grupos", data={"nome": "Estudo", "amigos": [b.id]}); assert r.status_code == 302
    g = GrupoChat.query.filter_by(is_direto=False).one()
    client.post("/mensagens/grupos", data={"nome": "X", "amigos": [9999]}); assert GrupoChat.query.count() == 1  # só amigos
    assert c2.post(f"/mensagens/{g.id}/adicionar", data={"amigo": a.id}).status_code == 302  # não-admin: recusado
    m = client.post(f"/mensagens/{g.id}/enviar", data={"texto": "ofensa"}).get_json()["mensagem"]
    c2.post(f"/mensagens/{g.id}/mensagem/{m['id']}/denunciar", data={"motivo": "ofensivo"})
    c2.post(f"/mensagens/{g.id}/mensagem/{m['id']}/denunciar", data={"motivo": "ofensivo"})
    assert Denuncia.query.filter_by(alvo_tipo="mensagem").count() == 1
    client.post(f"/mensagens/{g.id}/mensagem/{m['id']}/denunciar", data={"motivo": "spam"})  # da própria mensagem: não
    assert Denuncia.query.count() == 1
    client.post(f"/mensagens/{g.id}/sair")  # admin sai: outro vira admin
    assert [x.usuario_id for x in GrupoChat.query.get(g.id).membros if x.eh_admin] == [b.id]
    c2.post(f"/mensagens/{g.id}/sair")
    assert GrupoChat.query.filter_by(id=g.id).count() == 0 and Mensagem.query.count() == 0


def test_admin_oculta_mensagem_denunciada_e_bane_autor(app, client):
    a, b, c2 = _duas_contas(app, client)
    _amigos(client, c2, a, b)
    client.post(f"/mensagens/direta/{b.id}")
    g = GrupoChat.query.one()
    m = c2.post(f"/mensagens/{g.id}/enviar", data={"texto": "mensagem ofensiva"}).get_json()["mensagem"]
    client.post(f"/mensagens/{g.id}/mensagem/{m['id']}/denunciar", data={"motivo": "ofensivo", "detalhe": "x"})
    assert client.get("/admin/denuncias").status_code == 403           # aluno comum
    a.is_admin = True; db.session.commit()
    pagina = client.get("/admin/denuncias").data.decode()
    assert "mensagem ofensiva" in pagina and "Ocultar mensagem" in pagina
    d = Denuncia.query.one()
    client.post(f"/admin/denuncias/{d.id}/resolver", data={"acao": "ocultar"})
    assert Mensagem.query.one().deletado is True and Denuncia.query.one().status == "procedente"
    assert client.get(f"/mensagens/{g.id}/novas?depois=0").get_json()["mensagens"] == []  # some para todos
    db.session.add(Denuncia(autor_id=a.id, alvo_tipo="mensagem", alvo_id=m["id"], motivo="spam")); db.session.commit()
    d2 = Denuncia.query.filter_by(status="aberta").one()
    client.post(f"/admin/denuncias/{d2.id}/resolver", data={"acao": "banir"})
    assert Usuario.query.get(b.id).is_banido is True


def test_notificacao_so_aceita_link_interno_seguro(client):
    from app.models import Notificacao
    from app.services import notificacoes
    u = Usuario(username="n1", email="n1@x.com", nome="N", sobrenome="1", tag="0009", senha_hash="x")
    db.session.add(u); db.session.flush()
    for ruim in ("//evil.com", "/\\evil.com", "https://evil.com", "/ok\n", "javascript:alert(1)"):
        notificacoes.criar(u.id, "t", "x", url=ruim)
    notificacoes.criar(u.id, "t", "x", url="/amigos")
    db.session.commit()
    assert sorted(str(n.url) for n in Notificacao.query.all()) == ["/amigos"] + ["None"] * 5


def test_grupo_novo_membro_nao_le_o_que_veio_antes_e_bloqueio_impede_adicao(client):
    from datetime import timedelta
    from app import clock
    from app.models import Bloqueio
    from app.services import chat as svc
    def mk(n, t):
        u = Usuario(username=n, email=f"{n}@x.com", nome=n, sobrenome="S", tag=t, senha_hash="x"); db.session.add(u); db.session.flush(); return u
    a, b, c = mk("ga", "0011"), mk("gb", "0012"), mk("gc", "0013")
    for x, y in ((a, b), (a, c)):
        db.session.add(Amizade(solicitante_id=x.id, destinatario_id=y.id, status="aceito"))
    g = svc.criar_grupo(a, "Grupo", [b.id]); db.session.flush()
    for m in g.membros: m.entrou_em = clock.agora() - timedelta(hours=3)  # a e b já estavam lá
    antiga = svc.enviar(a, g, "segredo antigo"); antiga.enviado_em = clock.agora() - timedelta(hours=2)
    svc.adicionar(a, g, c.id); db.session.flush()
    nova = svc.enviar(a, g, "depois de c entrar")
    assert [m.conteudo for m in svc.mensagens(g, desde_quando=svc.desde(g, c.id))] == ["depois de c entrar"]
    assert "segredo antigo" in [m.conteudo for m in svc.mensagens(g, desde_quando=svc.desde(g, a.id))]  # quem já estava vê tudo
    assert svc.anteriores(g, nova.id, desde_quando=svc.desde(g, c.id))[0] == []
    # bloqueio entre o candidato e um membro atual impede a adição
    d = mk("gd", "0014"); db.session.add(Amizade(solicitante_id=a.id, destinatario_id=d.id, status="aceito"))
    db.session.add(Bloqueio(bloqueador_id=b.id, bloqueado_id=d.id))
    db.session.flush()
    import pytest
    with pytest.raises(svc.ErroChat):
        svc.adicionar(a, g, d.id)


def test_lista_de_conversas_nao_vaza_mensagem_anterior_a_entrada_e_grupo_respeita_bloqueio(client):
    """Achados hunter-04: prévia/contagem da lista sem o corte por entrada; criar_grupo sem checar bloqueio entre convidados."""
    from datetime import timedelta
    import pytest
    from app import clock
    from app.models import Bloqueio
    from app.services import chat as svc
    def mk(n, t):
        u = Usuario(username=n, email=f"{n}@x.com", nome=n, sobrenome="S", tag=t, senha_hash="x"); db.session.add(u); db.session.flush(); return u
    a, b, c = mk("la", "0021"), mk("lb", "0022"), mk("lc", "0023")
    for y in (b, c):
        db.session.add(Amizade(solicitante_id=a.id, destinatario_id=y.id, status="aceito"))
    g = svc.criar_grupo(a, "G", [b.id]); db.session.flush()
    for m in g.membros: m.entrou_em = clock.agora() - timedelta(hours=3)
    antiga = svc.enviar(a, g, "segredo antigo"); antiga.enviado_em = clock.agora() - timedelta(hours=2)
    svc.adicionar(a, g, c.id); db.session.flush()
    linha = [x for x in svc.conversas(c) if x["grupo"].id == g.id][0]
    assert linha["ultima"] is None and linha["nao_lidas"] == 0
    assert [x for x in svc.conversas(a) if x["grupo"].id == g.id][0]["ultima"].conteudo == "segredo antigo"
    db.session.add(Bloqueio(bloqueador_id=b.id, bloqueado_id=c.id)); db.session.flush()
    with pytest.raises(svc.ErroChat):
        svc.criar_grupo(a, "H", [b.id, c.id])
