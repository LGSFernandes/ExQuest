import threading

from sqlalchemy import select

from app.extensions import db
from app.models import InventarioItem, ItemLoja, LancamentoCarteira, Usuario
from app.services import catalogo, loja, wallet
from tests.test_auth import registrar


def _usuario(client, moedas=1000):
    registrar(client)
    u = Usuario.query.filter_by(email="ana@exemplo.com").one()
    if moedas:
        wallet.creditar(u.id, moedas, "ajuste", f"teste:{u.id}")
        db.session.commit()
    return u


def _item(css):
    return db.session.scalar(select(ItemLoja).where(ItemLoja.css_class == css))


def test_seed_idempotente_e_nao_altera_preco_existente(app):
    db.session.add(ItemLoja(nome="Borda Prata", descricao="x", tipo="borda", preco=9999, css_class="border-prata", slug="border-prata"))
    db.session.commit()
    c1, e1 = catalogo.semear(); db.session.commit()
    c2, e2 = catalogo.semear(); db.session.commit()
    assert c1 > 25 and e1 == 1 and c2 == 0 and e2 == c1 + 1
    assert _item("border-prata").preco == 9999
    assert ItemLoja.query.filter(ItemLoja.slug.is_(None)).count() == 0
    assert _item("border-galaxia").slug == "border-galaxia" and _item("badge-veterano")  # slugs usados nas recompensas de nível


def test_compra_debita_uma_vez_entrega_e_recusa_duplicada_ou_sem_saldo(client, app):
    catalogo.semear(); db.session.commit()
    u = _usuario(client, 300)
    prata = _item("border-prata")
    loja.comprar(u, prata.id, "t1"); db.session.commit()
    db.session.refresh(u)
    assert u.moedas == 300 - prata.preco and InventarioItem.query.filter_by(usuario_id=u.id).count() == 1
    try:
        loja.comprar(u, prata.id, "t2"); assert False
    except loja.ErroLoja as e:
        assert "já tem" in str(e)
    caro = _item("border-plasma")
    try:
        loja.comprar(u, caro.id, "t3"); assert False
    except loja.ErroLoja as e:
        assert "insuficientes" in str(e)
    db.session.rollback()
    assert wallet.conferir(u.id)[0]


def test_consumivel_repetir_mesmo_token_nao_cobra_duas_vezes(client, app):
    catalogo.semear(); db.session.commit()
    u = _usuario(client, 500)
    esc = db.session.scalar(select(ItemLoja).where(ItemLoja.tipo == "streak_shield", ItemLoja.valor_boost == 1))
    for _ in range(3):
        loja.comprar(u, esc.id, "mesmo-token"); db.session.commit()
    db.session.refresh(u)
    inv = InventarioItem.query.filter_by(usuario_id=u.id).one()
    assert inv.quantidade == 1 and u.moedas == 500 - esc.preco
    loja.comprar(u, esc.id, "outro-token"); db.session.commit()
    assert InventarioItem.query.filter_by(usuario_id=u.id).one().quantidade == 2


def test_compras_simultaneas_nao_gastam_mais_que_o_saldo(tmp_path):
    from app import create_app
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'l.db'}"})
    with app.app_context():
        db.create_all()
        catalogo.semear()
        u = Usuario(nome="A", sobrenome="B", username="ana", email="a@x.com", tag="AAAA", moedas=0)
        db.session.add(u); db.session.flush()
        wallet.creditar(u.id, 120, "saldo_inicial", "s:1")
        boost = db.session.scalar(select(ItemLoja).where(ItemLoja.nome == "Boost XP +50% (24h)"))  # custa 120
        db.session.commit()
        uid, bid = u.id, boost.id
    ok, barreira = [], threading.Barrier(6)

    def tenta(n):
        with app.app_context():
            barreira.wait()
            try:
                loja.comprar(db.session.get(Usuario, uid), bid, f"tk{n}"); db.session.commit(); ok.append(n)
            except loja.ErroLoja:
                db.session.rollback()
            except Exception:  # noqa: BLE001  (SQLITE_BUSY sob corrida também não pode cobrar)
                db.session.rollback()
            finally:
                db.session.remove()
    ts = [threading.Thread(target=tenta, args=(i,)) for i in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    with app.app_context():
        assert len(ok) == 1
        assert wallet.conferir(uid)[0] and db.session.get(Usuario, uid).moedas == 0
        assert InventarioItem.query.filter_by(usuario_id=uid).one().quantidade == 1
        db.session.remove(); db.engine.dispose()


def test_equipar_um_por_tipo_desequipar_e_item_alheio(client, app):
    catalogo.semear(); db.session.commit()
    u = _usuario(client, 2000)
    a, b = _item("fundo-pautado"), _item("fundo-lousa")
    for i in (a, b):
        loja.comprar(u, i.id, "t"); db.session.commit()
    loja.equipar(u, a.id); loja.equipar(u, b.id); db.session.commit()
    assert u.fundo_ativo == "fundo-lousa"
    assert [i.equipado for i in InventarioItem.query.join(ItemLoja).filter(ItemLoja.tipo == "fundo").order_by(ItemLoja.id)] == [False, True]
    try:
        loja.equipar(u, _item("border-galaxia").id); assert False  # não possui
    except loja.ErroLoja:
        pass
    loja.desequipar(u, "fundo"); db.session.commit()
    assert u.fundo_ativo is None


def test_usar_boost_so_uma_vez_enquanto_ativo_e_escudo_soma(client, app):
    catalogo.semear(); db.session.commit()
    u = _usuario(client, 2000)
    b = db.session.scalar(select(ItemLoja).where(ItemLoja.nome == "Boost XP +50% (24h)"))
    loja.comprar(u, b.id, "a"); loja.comprar(u, b.id, "b"); db.session.commit()
    loja.usar(u, b.id); db.session.commit()
    assert u.boost_xp_pct == 50 and u.boost_xp_atual >= 50
    try:
        loja.usar(u, b.id); assert False
    except loja.ErroLoja as e:
        assert "ativo" in str(e)
    esc = db.session.scalar(select(ItemLoja).where(ItemLoja.nome == "Escudo Duplo"))
    loja.comprar(u, esc.id, "c"); loja.usar(u, esc.id); db.session.commit()
    assert u.streak.escudos == 2
    try:
        loja.usar(u, esc.id); assert False
    except loja.ErroLoja:
        pass


def test_rotas_da_loja_exigem_csrf_login_e_renderizam(client, app):
    catalogo.semear(); db.session.commit()
    assert client.get("/loja/").status_code == 302 and client.post("/loja/comprar/1").status_code in (302, 400)
    u = _usuario(client, 500)
    for url in ("/loja/", "/loja/?tipo=fundo", "/loja/inventario"):
        r = client.get(url); assert r.status_code == 200 and b"style=" not in r.data, url
    prata = _item("border-prata")
    r = client.post(f"/loja/comprar/{prata.id}", data={"tk": "x"}, follow_redirects=True)
    assert b"comprado" in r.data
    client.post(f"/loja/equipar/{prata.id}")
    db.session.refresh(u)
    assert u.borda_ativa == "border-prata"
    assert b"avatar-moldura border-prata" in client.get("/loja/inventario").data


def test_perfil_camadas_privacidade_e_senha(client, app):
    catalogo.semear(); db.session.commit()
    u = _usuario(client, 20000)
    for css in ("fundo-lousa", "efeito-aurora", "border-galaxia", "badge-lenda"):
        loja.comprar(u, _item(css).id, "t"); db.session.commit(); loja.equipar(u, _item(css).id)
    db.session.commit()
    html = client.get("/perfil/ana").data.decode()
    # fundo e efeito são camadas irmãs ATRÁS do conteúdo; banner/avatar/botões ficam em .perfil-conteudo
    assert html.index("perfil-fundo fundo-lousa") < html.index("perfil-efeito efeito-aurora") < html.index("perfil-conteudo")
    assert "avatar-moldura border-galaxia" in html and "selo badge-lenda" in html and "style=" not in html
    assert 'class="perfil-banner' in html and html.index("perfil-conteudo") < html.index("perfil-banner")
    # privacidade: outro usuário não vê histórico/estatísticas quando ocultos
    u.mostrar_stats = u.mostrar_historico = False; db.session.commit()
    client.post("/sair")
    registrar(client, username="bia", email="bia@exemplo.com")
    h2 = client.get("/perfil/ana").data.decode()
    assert "Desempenho por matéria" not in h2 and "Últimas respostas" not in h2 and "perfil-fundo fundo-lousa" in h2
    assert client.get("/perfil/ninguem").status_code == 404
    # troca de senha exige a atual e mantém a sessão atual
    r = client.post("/configuracoes/senha", data={"s-senha_atual": "errada", "s-nova_senha": "outra-senha-forte-7", "s-confirmar": "outra-senha-forte-7"}, follow_redirects=True)
    assert b"incorreta" in r.data
    r = client.post("/configuracoes/senha", data={"s-senha_atual": "cavalo-bateria-9", "s-nova_senha": "outra-senha-forte-7", "s-confirmar": "outra-senha-forte-7"}, follow_redirects=True)
    assert b"Senha alterada" in r.data and client.get("/configuracoes").status_code == 200


def test_configuracoes_recursos_pagos_e_validacao_de_cor(client, app):
    u = _usuario(client, 0)
    base = {"acao": "perfil", "p-nome": "Ana", "p-sobrenome": "Souza", "p-biografia": "<b>oi</b>", "p-nick_fonte": "", "p-nick_cor": "#ff0000"}
    r = client.post("/configuracoes", data=base, follow_redirects=True)
    assert b"planos pagos" in r.data  # gratuito não ganha cor
    db.session.refresh(u)
    assert u.nick_cor is None and u.sobrenome == "Souza" and u.biografia == "<b>oi</b>"  # texto cru; o template escapa
    assert b"&lt;b&gt;oi" in client.get("/perfil/ana").data
    r = client.post("/configuracoes", data={**base, "p-nick_cor": "red;background:url(x)"})
    assert r.status_code == 200 and b"#RRGGBB" in r.data
    u.plano_premium, u.premium_expira = "inter", __import__("app.clock", fromlist=["x"]).agora().replace(year=2100)
    db.session.commit()
    client.post("/configuracoes", data=base)
    db.session.refresh(u)
    assert u.nick_cor == "#ff0000"
