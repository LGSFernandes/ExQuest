"""Ataques web contra a aplicação inteira (OWASP A01 acesso, A03 injeção, A05 configuração, A08 integridade, CSRF, XSS)."""
import io
import re

import pytest
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Alternativa, Materia, Questao, Usuario
from app.services import wallet
from tests.test_auth import DADOS

PUBLICAS = {"main.robots", "main.sitemap", "main.inicio", "main.termos", "main.privacidade", "main.saude", "auth.login", "auth.registro", "auth.recuperar", "auth.recuperar_enviado", "static"}


@pytest.fixture()
def app_csrf():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    from flask import g
    # o contexto da fixture é compartilhado entre requisições do test client; em produção cada requisição tem o seu `g`
    app.before_request(lambda: g.pop("csrf_token", None) and None)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _token(c, url="/entrar"):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*name="csrf_token"', c.get(url).data.decode()).group(0).split('value="')[1].split('"')[0]


def _logar_csrf(c):
    c.post("/cadastro", data={**DADOS, "csrf_token": _token(c, "/cadastro")})
    return Usuario.query.filter_by(email=DADOS["email"]).one()


def test_todo_post_exige_csrf_inclusive_json_e_webhook_so_pela_assinatura(app_csrf):
    c = app_csrf.test_client()
    u = _logar_csrf(c)
    m = Materia(nome="M"); db.session.add(m); db.session.flush()
    q = Questao(enunciado="x", materia_id=m.id); q.alternativas = [Alternativa(texto="a", correta=True)]
    db.session.add(q); wallet.creditar(u.id, 500, "ajuste", "s"); db.session.commit()
    alt = q.alternativas[0].id
    assert c.post("/questoes/responder", json={"questao_id": q.id, "alternativa_id": alt}).status_code == 400  # sem token
    meta = re.search(r'name="csrf-token" content="([^"]+)"', c.get("/").data.decode()).group(1)
    ok = c.post("/questoes/responder", json={"questao_id": q.id, "alternativa_id": alt}, headers={"X-CSRFToken": meta})
    assert ok.status_code == 200 and ok.get_json()["acertou"], ok.data[:300]
    for url in ("/loja/comprar/1", "/loja/equipar/1", "/loja/usar/1", "/simulados/iniciar", "/pagamentos/checkout", "/configuracoes", "/configuracoes/senha", "/sair"):
        assert c.post(url).status_code == 400, url
    assert Usuario.query.get(u.id).moedas >= 500
    # webhooks não usam CSRF, mas sem assinatura nada acontece
    assert c.post("/webhooks/stripe", data=b"{}").status_code == 400 and c.post("/webhooks/mercadopago", json={}).status_code == 400


def test_nenhuma_rota_get_privada_abre_sem_login(app):
    c = app.test_client()
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.endpoint in PUBLICAS or any(a for a in rule.arguments):
            continue
        r = c.get(rule.rule)
        assert r.status_code in (302, 401, 404, 405), (rule.rule, r.status_code)
        if r.status_code == 302:
            assert "/entrar" in r.headers["Location"], rule.rule


def test_rotas_com_id_exigem_login_e_dono(app):
    c = app.test_client()
    for url in ("/perfil/ana", "/simulados/abc", "/pagamentos/retorno/1"):
        assert c.get(url).status_code in (302, 401), url


def test_cookies_e_cabecalhos(client):
    r = client.post("/cadastro", data=DADOS)
    ck = "; ".join(r.headers.getlist("Set-Cookie"))
    assert "HttpOnly" in ck and "SameSite=Lax" in ck
    h = client.get("/").headers
    assert h["X-Content-Type-Options"] == "nosniff" and "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "Referrer-Policy" in h and "Server" not in {k for k in h.keys() if k == "X-Powered-By"}


def test_xss_armazenado_nome_e_biografia_saem_escapados_em_todas_as_telas(client):
    client.post("/cadastro", data={**DADOS, "nome": "<script>alert(1)</script>"})
    u = Usuario.query.one()
    u.nome, u.biografia, u.xp = '"><img src=x onerror=alert(1)>', "<svg onload=alert(1)>", 50
    db.session.commit()
    for url in ("/", "/perfil/ana", "/ranking/", "/configuracoes"):
        h = client.get(url).data.decode()
        assert "<script>alert" not in h and "<img src=x" not in h and "<svg onload" not in h, url


def test_injecao_sql_e_entradas_hostis_nos_filtros_nao_quebram(client):
    client.post("/cadastro", data=DADOS)
    m = Materia(nome="M"); db.session.add(m); db.session.commit()
    for v in ("' OR 1=1 --", "%", "_" * 200, "\x00", "'; DROP TABLE usuarios; --"):
        assert client.get("/questoes/", query_string={"materia_id": m.id, "conteudo": v, "dificuldade": v, "tipo": v}).status_code == 200
        assert client.get("/ranking/", query_string={"periodo": v, "page": v}).status_code in (200, 404)
    assert client.get("/ranking/?page=999999999999999999999").status_code == 200
    assert Usuario.query.count() == 1


def test_traversal_e_dados_privados_nao_sao_servidos(client):
    for url in ("/static/../instance/database.db", "/static/%2e%2e/%2e%2e/.env", "/static/data/chat/x.png", "/.env", "/instance/database.db", "/static/../app/config.py"):
        assert client.get(url).status_code == 404, url


def test_mass_assignment_em_configuracoes_nao_altera_saldo_nem_papel(client):
    client.post("/cadastro", data=DADOS)
    u = Usuario.query.one()
    antes = (u.xp, u.moedas, u.is_admin, u.plano_premium, u.is_banido)
    client.post("/configuracoes", data={"acao": "perfil", "p-nome": "Ana", "p-sobrenome": "Souza", "xp": "999999", "moedas": "999999", "is_admin": "1",
                                        "plano_premium": "advan", "p-xp": "999999", "p-is_admin": "y"})
    db.session.refresh(u)
    assert (u.xp, u.moedas, u.is_admin, u.plano_premium, u.is_banido) == antes


def test_upload_poliglota_e_svg_com_extensao_de_imagem_sao_recusados(client):
    client.post("/cadastro", data=DADOS)
    u = Usuario.query.one()
    base = {"acao": "perfil", "p-nome": "Ana", "p-sobrenome": "Souza"}
    for conteudo in (b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", b"GIF89a<script>alert(1)</script>", b"<?php system($_GET[0]); ?>"):
        r = client.post("/configuracoes", data={**base, "p-icon_file": (io.BytesIO(conteudo), "foto.png")}, content_type="multipart/form-data", follow_redirects=True)
        db.session.refresh(u)
        assert u.icon_path is None, conteudo
    assert client.post("/configuracoes", data={**base, "p-icon_file": (io.BytesIO(b"x" * (13 * 1024 * 1024)), "g.png")}, content_type="multipart/form-data").status_code == 413


def test_erros_nao_vazam_detalhes_internos(app):
    @app.route("/_boom")
    def _boom():
        raise RuntimeError("segredo-interno-123 /home/claude")
    client = app.test_client()
    r = client.get("/perfil/<script>x</script>")
    assert b"<script>x" not in r.data
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = client.get("/_boom")
    assert r.status_code == 500 and b"segredo-interno" not in r.data and b"Traceback" not in r.data


def test_robots_e_sitemap_so_listam_paginas_publicas(client):
    assert "Disallow: /webhooks/" in client.get("/robots.txt").data.decode()
    sm = client.get("/sitemap.xml").data.decode()
    assert "/termos" in sm and "/perfil" not in sm and "/loja" not in sm


def test_seo_manifest_e_jsonld_na_landing(client):
    import json, re
    html = client.get("/").data.decode()
    assert 'rel="manifest"' in html and 'property="og:description"' in html
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert ld["@type"] == "WebApplication"
    assert client.get("/static/img/site.webmanifest").status_code == 200
    assert json.loads(client.get("/static/img/site.webmanifest").data)["start_url"] == "/"


def test_next_do_login_rejeita_normalizacao_que_vira_protocolo_relativo(app):
    from app.security import url_interna_segura
    with app.test_request_context("/entrar", base_url="http://exquest.test"):
        for ruim in ("/.//evil.com", "//evil.com", "/\\evil.com", "https://evil.com/x", "/./\\evil.com"):
            assert url_interna_segura(ruim) == "/", ruim
        assert url_interna_segura("/questoes/?a=1") == "/questoes/?a=1"


def test_link_de_redefinicao_usa_base_url_e_nao_o_host_da_requisicao(client, app, monkeypatch):
    from app.models import Usuario
    from app.services import auth as svc
    from tests.test_auth import registrar
    registrar(client)
    client.post("/sair")
    enviados = []
    monkeypatch.setattr(svc, "enviar_email_recuperacao", lambda u, link: enviados.append(link))
    client.post("/recuperar-senha", data={"email": "ana@exemplo.com"}, headers={"Host": "evil.test", "X-Forwarded-Host": "evil.test"})
    assert enviados and enviados[0].startswith(app.config["BASE_URL"] + "/redefinir-senha/") and "evil.test" not in enviados[0]


def test_google_vinculando_conta_com_senha_derruba_senha_e_sessoes(client, app, monkeypatch):
    from app.blueprints import auth as bauth
    from app.models import Usuario
    from tests.test_auth import registrar
    registrar(client)
    client.post("/sair")
    u = Usuario.query.filter_by(email="ana@exemplo.com").one(); sv = u.session_version or 0
    class G:
        def authorize_access_token(self): return {"userinfo": {"email": "ana@exemplo.com", "sub": "g-1", "email_verified": True}}
    monkeypatch.setattr(bauth, "_google_ativo", lambda: True)
    monkeypatch.setattr(bauth.oauth, "google", G(), raising=False)
    client.get("/entrar/google/retorno")
    u = Usuario.query.filter_by(email="ana@exemplo.com").one()
    assert u.google_id == "g-1" and u.senha_hash is None and (u.session_version or 0) == sv + 1
