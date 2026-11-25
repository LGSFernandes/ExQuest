import re

from app.extensions import db
from app.models import TokenRecuperacao, Usuario
from app.services import auth as svc

DADOS = dict(nome="Ana", sobrenome="Silva", username="ana", email="ana@exemplo.com", senha="cavalo-bateria-9",
             confirmar_senha="cavalo-bateria-9", aceito="y")


def registrar(client, **kw):
    return client.post("/cadastro", data={**DADOS, **kw}, follow_redirects=False)


def test_paginas_publicas_renderizam_com_cabecalhos_de_seguranca(client):
    for url in ("/", "/entrar", "/cadastro", "/recuperar-senha", "/termos", "/inexistente"):
        r = client.get(url)
        assert r.status_code in (200, 404), url
        assert "script-src 'self'" in r.headers["Content-Security-Policy"]
        assert "'unsafe-inline'" not in r.headers["Content-Security-Policy"]
        assert r.headers["X-Frame-Options"] == "DENY"
        assert b"style=" not in r.data, f"estilo inline em {url}"  # CSP bloquearia


def test_registro_cria_conta_senha_em_hash_e_entra(client, app):
    r = registrar(client)
    assert r.status_code == 302
    u = Usuario.query.filter_by(email="ana@exemplo.com").one()
    assert u.senha_hash.startswith("$2") and "cavalo" not in u.senha_hash and len(u.tag) == 4
    assert client.get("/").status_code == 200  # painel autenticado


def test_registro_rejeita_senha_fraca_duplicado_e_xss_no_username(client):
    assert b"muito comum" in registrar(client, senha="password", confirmar_senha="password").data
    assert registrar(client, username="<script>x</script>").status_code == 200
    assert Usuario.query.count() == 0
    registrar(client)
    client.post("/sair")
    r = registrar(client, username="outra")  # mesmo e-mail
    assert b"j\xc3\xa1 est\xc3\xa1 cadastrado" in r.data and Usuario.query.count() == 1


def test_login_mensagem_generica_e_bloqueio_por_tentativas(client):
    registrar(client); client.post("/sair")
    r1 = client.post("/entrar", data={"email": "ana@exemplo.com", "senha": "errada"})
    r2 = client.post("/entrar", data={"email": "ninguem@exemplo.com", "senha": "errada"})
    assert r1.status_code == r2.status_code == 401 and b"incorretos" in r1.data and b"incorretos" in r2.data
    for _ in range(8):
        client.post("/entrar", data={"email": "ana@exemplo.com", "senha": "errada"})
    r = client.post("/entrar", data={"email": "ana@exemplo.com", "senha": DADOS["senha"]})  # senha certa, mas bloqueada
    assert r.status_code == 429


def test_login_next_externo_e_ignorado_e_logout_exige_post(client):
    registrar(client); client.post("/sair")
    r = client.post("/entrar?next=https://evil.example/x", data={"email": "ana@exemplo.com", "senha": DADOS["senha"]})
    assert r.status_code == 302 and r.headers["Location"] == "/"
    assert client.get("/sair").status_code == 405
    assert client.post("/sair").status_code == 302


def test_banido_nao_entra(client):
    registrar(client); client.post("/sair")
    Usuario.query.update({"is_banido": True}); db.session.commit()
    assert client.post("/entrar", data={"email": "ana@exemplo.com", "senha": DADOS["senha"]}).status_code == 403


def test_recuperacao_token_em_hash_uso_unico_e_derruba_sessoes(client, app, caplog):
    registrar(client)
    u = Usuario.query.one(); sv0 = u.session_version
    client.post("/sair")
    client.get("/entrar")  # consome o aviso "Você saiu"
    caplog.set_level("WARNING")
    # mesma resposta para e-mail existente e inexistente
    a = client.post("/recuperar-senha", data={"email": "ana@exemplo.com"})
    b = client.post("/recuperar-senha", data={"email": "x@exemplo.com"})
    assert a.status_code == b.status_code == 200 and a.data == b.data
    token = re.search(r"/redefinir-senha/([\w-]+)", caplog.text).group(1)
    assert TokenRecuperacao.query.one().token != token  # só o hash fica no banco
    r = client.post(f"/redefinir-senha/{token}", data={"nova_senha": "outra-senha-forte-7", "confirmar_senha": "outra-senha-forte-7"})
    assert r.status_code == 302
    assert client.get(f"/redefinir-senha/{token}").status_code == 302  # já usado
    db.session.expire_all()
    assert Usuario.query.one().session_version == sv0 + 1
    assert client.post("/entrar", data={"email": "ana@exemplo.com", "senha": "outra-senha-forte-7"}).status_code == 302


def test_sessao_antiga_cai_quando_session_version_muda(client):
    registrar(client)
    assert client.get("/").status_code == 200
    Usuario.query.update({"session_version": 5}); db.session.commit()
    r = client.get("/")
    assert b"Criar conta" in r.data  # caiu para a landing (deslogado)


def test_titulo_e_robots_vem_da_pagina(client):
    assert b"<title>Entrar" in client.get("/entrar").data
    assert b'name="robots" content="noindex"' in client.get("/entrar").data
    termos = client.get("/termos").data
    assert b"<title>Termos de uso" in termos and b"noindex" not in termos
    registrar(client)
    assert b'name="robots" content="noindex"' in client.get("/").data  # área logada fora dos buscadores


def test_token_cru_no_banco_nao_vale_e_consumo_e_atomico(client, app):
    from datetime import timedelta
    from app.services import auth as svc
    from app import clock
    registrar(client)
    u = Usuario.query.filter_by(email=DADOS["email"]).one()
    db.session.add(TokenRecuperacao(usuario_id=u.id, token="legado-em-claro", expira=clock.agora() + timedelta(hours=1)))
    db.session.commit()
    assert svc.token_valido("legado-em-claro") is None  # só o hash é aceito
    token = svc.criar_token_recuperacao(u)
    db.session.commit()
    t = svc.token_valido(token)
    # segunda requisição já gastou o token: a cópia em memória da primeira não pode trocar a senha de novo
    TokenRecuperacao.query.filter_by(id=t.id).update({"usado": True}); db.session.commit()
    antes = u.senha_hash
    assert svc.redefinir_senha(t, "outra-senha-forte-7") is False and u.senha_hash == antes


def test_cookie_lembrar_nao_sobrevive_a_troca_de_senha(app):
    """Achado hunter-03: o cookie 'lembrar de mim' guardava só o id e ignorava session_version."""
    from flask_login import current_user
    c1 = app.test_client()
    registrar(c1)
    c1.post("/sair")
    c1.post("/entrar", data={"email": DADOS["email"], "senha": DADOS["senha"], "lembrar": "y"})
    cookie = c1.get_cookie("remember_token").value

    def autenticado():  # requisição nova que traz SÓ o cookie "lembrar" (sem cookie de sessão)
        from flask import g
        g.pop("_login_user", None)  # o app context do teste é compartilhado: não reaproveitar o usuário da chamada anterior
        with app.test_request_context("/configuracoes", headers={"Cookie": "remember_token=" + cookie}):
            return current_user.is_authenticated

    assert autenticado() is True  # controle: antes da troca o cookie vale
    u = Usuario.query.filter_by(email=DADOS["email"]).one()
    u.session_version += 1; db.session.commit()  # o que a troca/recuperação de senha faz
    assert autenticado() is False
