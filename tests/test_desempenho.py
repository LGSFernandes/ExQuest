"""Compressão, versionamento de estáticos, CDN, cabeçalhos de cache, pool e cache de dados."""
import gzip

import brotli
import pytest

from app import cache, config as cfg, create_app
from app.hooks import montar_csp


def test_static_ganha_hash_e_cache_de_um_ano(client):
    html = client.get("/entrar").get_data(as_text=True)
    import re
    m = re.search(r'href="(/static/css/tokens\.css\?v=[0-9a-f]{10})"', html)
    assert m, "o CSS precisa sair com ?v=hash"
    r = client.get(m.group(1))
    assert r.status_code == 200
    assert "max-age=31536000" in r.headers["Cache-Control"] and "immutable" in r.headers["Cache-Control"]
    # sem versão: cache curto (não pode ficar velho por um ano)
    assert "max-age=86400" in client.get("/static/css/tokens.css").headers["Cache-Control"]


def test_css_e_comprimido_com_brotli_ou_gzip(client):
    r = client.get("/static/css/components.css", headers={"Accept-Encoding": "br, gzip"})
    assert r.headers["Content-Encoding"] == "br" and "Accept-Encoding" in r.headers["Vary"]
    plano = open("app/static/css/components.css", "rb").read()
    assert brotli.decompress(r.data) == plano and len(r.data) < len(plano) / 3
    g = client.get("/static/css/components.css", headers={"Accept-Encoding": "gzip"})
    assert g.headers["Content-Encoding"] == "gzip" and gzip.decompress(g.data) == plano


def test_html_so_e_comprimido_em_get_sem_query(client):
    ok = client.get("/entrar", headers={"Accept-Encoding": "gzip"})
    assert ok.headers.get("Content-Encoding") == "gzip"
    # com query string o HTML pode ecoar entrada do usuário: não comprime (BREACH)
    assert "Content-Encoding" not in client.get("/entrar?x=1", headers={"Accept-Encoding": "gzip"}).headers
    # fontes e imagens já comprimidas não são recomprimidas
    assert "Content-Encoding" not in client.get("/static/fonts/literata-latin-wght-normal.woff2", headers={"Accept-Encoding": "gzip"}).headers


def test_cdn_reescreve_urls_e_ajusta_csp():
    app = create_app("testing", {"CDN_URL": "https://cdn.exemplo.com"})
    with app.app_context():
        c = app.test_client()
        r = c.get("/entrar")
        corpo = r.get_data(as_text=True)
        assert 'href="https://cdn.exemplo.com/static/css/tokens.css?v=' in corpo
        assert "script-src 'self' https://cdn.exemplo.com" in r.headers["Content-Security-Policy"]
        assert "connect-src 'self'" in r.headers["Content-Security-Policy"]  # conexões de dados continuam só no próprio domínio
    assert "cdn" not in montar_csp()


def test_pool_so_para_bancos_servidor():
    c = cfg.Config()
    assert cfg.engine_options("sqlite:///x.db", c) == {"pool_pre_ping": True}
    pg = cfg.engine_options("postgresql+psycopg://u:p@h/db", c)
    assert pg["pool_size"] == 10 and pg["max_overflow"] == 20 and pg["pool_recycle"] == 1800 and pg["pool_pre_ping"]
    assert pg["connect_args"]["connect_timeout"] == 5 and "statement_timeout=15000" in pg["connect_args"]["options"]


def test_cache_memoria_ttl_e_geracao(app):
    cache.limpar_tudo_memoria()
    n = {"c": 0}

    def calc():
        n["c"] += 1
        return {"v": n["c"]}
    assert cache.obter("t", "a", 60, calc) == {"v": 1}
    assert cache.obter("t", "a", 60, calc) == {"v": 1} and n["c"] == 1
    cache.invalidar("t")
    assert cache.obter("t", "a", 60, calc) == {"v": 2}
    app.config["CACHE_DESLIGADO"] = True
    assert cache.obter("t", "a", 60, calc) == {"v": 3}


def test_cache_redis_real_e_queda_do_redis_nao_derruba():
    import shutil
    import subprocess
    import time
    if not shutil.which("redis-server"):
        pytest.skip("redis-server ausente")
    p = subprocess.Popen(["redis-server", "--port", "6391", "--save", "", "--appendonly", "no"], stdout=subprocess.DEVNULL)
    try:
        time.sleep(0.6)
        app = create_app("testing", {"REDIS_URL": "redis://127.0.0.1:6391/0", "CACHE_PREFIXO": "tst"})
        with app.app_context():
            n = {"c": 0}

            def calc():
                n["c"] += 1
                return [1, 2, n["c"]]
            assert cache.obter("r", "x", 30, calc) == [1, 2, 1]
            assert cache.obter("r", "x", 30, calc) == [1, 2, 1] and n["c"] == 1  # veio do Redis
            cache.invalidar("r")
            assert cache.obter("r", "x", 30, calc) == [1, 2, 2]
            import redis
            assert redis.Redis(port=6391).keys("tst:r:*")  # as chaves existem de fato no Redis
            p.terminate(); p.wait(5)
            assert cache.obter("r", "x", 30, calc)[2] >= 3  # Redis caiu: recalcula em vez de dar erro
    finally:
        p.terminate()


# --- fila de jobs ---------------------------------------------------------------------------
def test_job_eager_executa_na_hora_e_queue_grava_e_worker_executa(app):
    from app.extensions import db, outbox
    from app.models import Job
    from app.services import jobs
    outbox.clear()
    jobs.enfileirar("email", {"to": "a@x.com", "subject": "S", "body": "B"})
    assert outbox and not db.session.query(Job).count()  # eager: nada na fila
    outbox.clear()
    app.config["JOBS_MODE"] = "queue"
    j = jobs.enfileirar("email", {"to": "b@x.com", "subject": "S", "body": "link-secreto"})
    db.session.commit()
    assert not outbox and j.status == "pendente"
    assert jobs.executar_pendentes() == {"ok": 1, "falha": 0, "morto": 0}
    db.session.refresh(j)
    assert j.status == "ok" and j.payload_json == "{}" and outbox[0]["to"] == "b@x.com"  # payload apagado após o uso


def test_job_com_falha_reagenda_com_espera_e_morre_ao_esgotar(app, monkeypatch):
    from datetime import timedelta
    from app import clock
    from app.extensions import db
    from app.services import jobs
    app.config["JOBS_MODE"] = "queue"
    monkeypatch.setitem(jobs.HANDLERS, "email", lambda p: (_ for _ in ()).throw(RuntimeError("smtp fora")))
    j = jobs.enfileirar("email", {"to": "c@x.com", "subject": "S", "body": "B"}, max_tentativas=2)
    db.session.commit()
    assert jobs.executar_pendentes()["falha"] == 1
    db.session.refresh(j)
    assert j.status == "pendente" and j.tentativas == 1 and "smtp fora" in j.erro and j.proxima_em > clock.agora()
    assert jobs.executar_pendentes() == {"ok": 0, "falha": 0, "morto": 0}  # ainda dentro da espera
    j.proxima_em = clock.agora() - timedelta(seconds=1)
    db.session.commit()
    assert jobs.executar_pendentes()["morto"] == 1
    db.session.refresh(j)
    assert j.status == "morto" and j.tentativas == 2


def test_job_preso_volta_para_a_fila_e_dois_workers_nao_pegam_o_mesmo(app):
    from datetime import timedelta
    from app import clock
    from app.extensions import db
    from app.models import Job
    from app.services import jobs
    app.config["JOBS_MODE"] = "queue"
    j = jobs.enfileirar("email", {"to": "d@x.com", "subject": "S", "body": "B"})
    db.session.commit()
    assert jobs._reivindicar(j.id) is True
    assert jobs._reivindicar(j.id) is False  # segundo worker perde a disputa
    j.iniciado_em = clock.agora() - timedelta(minutes=11)
    db.session.commit()
    assert jobs._liberar_presos() == 1
    assert db.session.get(Job, j.id).status == "pendente"


def test_recuperacao_de_senha_usa_a_fila_sem_diferenca_de_resposta(client, app):
    from app.extensions import db, outbox
    from app.models import Job, Usuario
    app.config.update(MAIL_SERVER="smtp.teste", JOBS_MODE="queue")
    db.session.add(Usuario(nome="A", sobrenome="B", username="ana", email="ana@x.com", tag="0001", senha_hash="x"))
    db.session.commit()
    a = client.post("/recuperar-senha", data={"email": "ana@x.com"})
    b = client.post("/recuperar-senha", data={"email": "nao@x.com"})
    assert a.status_code == b.status_code == 200 and a.data == b.data
    assert db.session.query(Job).count() == 1 and not outbox  # só o e-mail existente gera job; nada é enviado na requisição


# --- imagens: WebP e redução -------------------------------------------------------------------
def _png_bytes(tam, modo="RGB", cor=(10, 120, 200)):
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.effect_noise(tam, 60).convert(modo).save(b, "PNG") if modo == "RGB" else Image.new(modo, tam, (10, 120, 200, 128)).save(b, "PNG")
    return b.getvalue()


def test_upload_vira_webp_reduzido_e_preserva_alpha(app, tmp_path):
    import io
    from PIL import Image
    from werkzeug.datastructures import FileStorage
    from app.services import uploads
    app.config["UPLOAD_ROOT"] = str(tmp_path / "up")
    bruto = _png_bytes((900, 700))
    nome = uploads.salvar_imagem(FileStorage(io.BytesIO(bruto), filename="a.png"), "icon", permitir_gif=False)
    arq = tmp_path / "up" / "icon" / nome
    im = Image.open(arq)
    assert nome.endswith(".webp") and im.format == "WEBP" and max(im.size) == 256 and arq.stat().st_size < len(bruto) / 4
    nome2 = uploads.salvar_imagem(FileStorage(io.BytesIO(_png_bytes((50, 50), "RGBA")), filename="a.png"), "icon", permitir_gif=False)
    assert Image.open(tmp_path / "up" / "icon" / nome2).mode == "RGBA"  # transparência continua


def test_cli_otimiza_uploads_antigos_sem_perder_referencia(app, tmp_path):
    import io
    from PIL import Image
    from app.extensions import db
    from app.models import Usuario
    app.config["UPLOAD_ROOT"] = str(tmp_path / "up")
    pasta = tmp_path / "up" / "icon"; pasta.mkdir(parents=True)
    (pasta / "ic_velho.png").write_bytes(_png_bytes((800, 800)))
    db.session.add(Usuario(nome="A", sobrenome="B", username="ana", email="a@x.com", tag="0001", senha_hash="x", icon_path="ic_velho.png"))
    db.session.commit()
    runner = app.test_cli_runner()
    r = runner.invoke(args=["imagens-otimizar"])  # simulação: nada muda
    assert "seriam convertidas" in r.output and (pasta / "ic_velho.png").exists()
    assert Usuario.query.one().icon_path == "ic_velho.png" and len(list(pasta.iterdir())) == 1
    r = runner.invoke(args=["imagens-otimizar", "--aplicar"])
    assert "1 imagem(ns) convertida(s)" in r.output
    novo = Usuario.query.one().icon_path
    assert novo.endswith(".webp") and (pasta / novo).exists() and not (pasta / "ic_velho.png").exists()
    assert Image.open(pasta / novo).format == "WEBP"


# --- cache de dados quentes --------------------------------------------------------------------
def test_ranking_e_materias_em_cache_com_invalidacao_e_sem_banido(app, client):
    from sqlalchemy import event
    from app.extensions import db
    from app.models import Materia, Usuario
    from app.services import destaques
    from tests.test_auth import registrar
    registrar(client)
    eu = Usuario.query.one(); eu.xp = 50
    outro = Usuario(nome="Bia", sobrenome="L", username="bia", email="b@x.com", tag="0002", senha_hash="x", xp=90)
    m = Materia(nome="Hist", cor="#111111")
    db.session.add_all([outro, m]); db.session.commit()
    n = [0]
    event.listen(db.engine, "before_cursor_execute", lambda *a: n.__setitem__(0, n[0] + 1))
    primeira = client.get("/ranking/"); q1 = n[0]; n[0] = 0
    segunda = client.get("/ranking/"); q2 = n[0]
    assert "bia" in primeira.get_data(as_text=True) and q2 < q1  # a segunda saiu do cache (menos consultas)
    assert "Hist" in segunda.get_data(as_text=True)
    outro.is_banido = True; db.session.commit()
    assert "bia" not in client.get("/ranking/").get_data(as_text=True)  # banido some mesmo com o cálculo em cache
    m.nome = "Historia2"; db.session.commit()
    assert "Hist" in client.get("/ranking/").get_data(as_text=True)  # ainda em cache (TTL)
    destaques.materias_mudaram()
    assert "Historia2" in client.get("/ranking/").get_data(as_text=True)


# --- observabilidade ---------------------------------------------------------------------------
def test_requisicao_lenta_e_registrada_sem_query_string(app, client, caplog):
    import logging
    app.config["SLOW_REQUEST_MS"] = 0
    with caplog.at_level(logging.WARNING, logger="exquest.lento"):
        client.get("/entrar?email=segredo@x.com")
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "requisição lenta" in msg and "auth.login" in msg and "consultas" in msg and "segredo" not in msg


def test_otel_gera_spans_de_flask_sql_e_http_externo():
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exp = InMemorySpanExporter()
    prov = TracerProvider()
    prov.add_span_processor(SimpleSpanProcessor(exp))
    app = create_app("testing", {"OTEL_ENABLED": False})
    app.extensions["otel_provider"] = prov
    from app import telemetry
    from app.extensions import db
    with app.app_context():
        db.create_all()
        telemetry._iniciar_otel(app, db.engine)
        app.test_client().get("/entrar")
        db.session.execute(db.text("select 1"))
    nomes = {s.name for s in exp.get_finished_spans()}
    assert any("GET" in n for n in nomes) and any(n.upper().startswith(("SELECT", "PRAGMA", "CONNECT")) or "select" in n.lower() for n in nomes), nomes


# --- RUM, healthz e admin ----------------------------------------------------------------------
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.data == b"ok" and r.headers["Cache-Control"] == "no-store"


def test_rum_valida_tudo_e_grava_so_o_valido(client, app):
    from app.models import MetricaRum
    ok = {"rota": "questoes.index", "d": "movel", "c": "4g", "m": {"LCP": 1800, "CLS": 0.05, "INP": 120, "FCP": 900, "TTFB": 300}}
    assert client.post("/rum", json=ok).status_code == 204 and MetricaRum.query.count() == 5
    ruim = [
        {**ok, "rota": "nao.existe"}, {**ok, "rota": "static"}, {**ok, "rota": "x" * 70}, {**ok, "d": "tv"}, {**ok, "c": "5g"},
        {**ok, "m": {"LCP": -1}}, {**ok, "m": {"LCP": 10 ** 9}}, {**ok, "m": {"XSS": 5}}, {**ok, "m": {"LCP": "<b>"}}, {**ok, "m": {"LCP": True}},
        {**ok, "m": []}, [1, 2],
    ]
    for corpo in ruim:
        assert client.post("/rum", json=corpo).status_code in (400,), corpo
    assert client.post("/rum", data="não é json", content_type="text/plain").status_code == 400
    assert client.post("/rum", json={**ok, "pad": "x" * 2000}).status_code == 204 and MetricaRum.query.count() == 5  # grande demais: descartado
    assert MetricaRum.query.count() == 5  # nada inválido foi gravado


def test_rum_desligado_nao_grava(client, app):
    from app.models import MetricaRum
    app.config["RUM_ENABLED"] = False
    client.post("/rum", json={"rota": "main.painel", "d": "movel", "c": "", "m": {"LCP": 1}})
    assert MetricaRum.query.count() == 0


def test_resumo_p75_e_pagina_admin(client, admin_logado):
    from app.extensions import db
    from app.models import MetricaRum
    from app.services import rum
    for v in (1000, 1200, 1400, 3000):
        db.session.add(MetricaRum(rota="main.painel", nome="LCP", valor=v, dispositivo="movel", conexao="3g"))
    db.session.commit()
    r = rum.resumo()
    assert r == [{"rota": "main.painel", "nome": "LCP", "amostras": 4, "p75": 3000.0, "nivel": "medio"}]
    assert rum.classificar("CLS", 0.3) == "ruim" and rum.classificar("INP", 100) == "bom"
    html = admin_logado.get("/admin/desempenho").get_data(as_text=True)
    assert "main.painel" in html and "3000 ms" in html
    assert rum.limpar_antigos(0) == 4


# --- busca ao vivo, autocomplete e histórico paginado -----------------------------------------------
def test_admin_questoes_devolve_fragmento_so_quando_pedido(admin_logado):
    from app.extensions import db
    from app.models import Alternativa, Materia, Questao
    m = Materia(nome="Fis", cor="#123456"); db.session.add(m); db.session.flush()
    for i in range(3):
        q = Questao(enunciado=f"Pergunta numero {i}", materia_id=m.id, dificuldade="facil", conteudo="c")
        q.alternativas = [Alternativa(texto="a", correta=True), Alternativa(texto="b")]
        db.session.add(q)
    db.session.commit()
    cheia = admin_logado.get("/admin/questoes?q=numero").get_data(as_text=True)
    parte = admin_logado.get("/admin/questoes?q=numero", headers={"X-Fragmento": "1"})
    assert "<html" in cheia and "data-busca-viva" in cheia and 'data-resultado' in cheia
    txt = parte.get_data(as_text=True)
    assert "<html" not in txt and "Pergunta numero 2" in txt and "Pergunta numero 0" in txt
    assert "Pergunta numero" not in admin_logado.get("/admin/questoes?q=zzz", headers={"X-Fragmento": "1"}).get_data(as_text=True)
    assert "Nenhuma questão encontrada" in admin_logado.get("/admin/questoes?q=zzz", headers={"X-Fragmento": "1"}).get_data(as_text=True)


def test_sugestoes_de_assunto(admin_logado):
    from app.extensions import db
    from app.models import Alternativa, Materia, Questao
    m = Materia(nome="Mat", cor="#123456"); oculta = Materia(nome="Oculta", cor="#123456", ativo=False)
    db.session.add_all([m, oculta]); db.session.flush()
    for assunto, mat, ativo in (("Funções do 2º grau", m, True), ("Funções exponenciais", m, True), ("Funções secretas", oculta, True), ("Geometria", m, True), ("Funções antigas", m, False)):
        q = Questao(enunciado="x", materia_id=mat.id, dificuldade="facil", conteudo=assunto, ativo=ativo)
        q.alternativas = [Alternativa(texto="a", correta=True), Alternativa(texto="b")]
        db.session.add(q)
    db.session.commit()
    r = admin_logado.get("/questoes/sugestoes?q=funç")
    assert r.get_json()["itens"] == ["Funções do 2º grau", "Funções exponenciais"]  # sem matéria oculta nem questão inativa
    assert admin_logado.get("/questoes/sugestoes?q=f").get_json()["itens"] == []  # mínimo de 2 letras
    assert admin_logado.get("/questoes/sugestoes?q=%25%25").get_json()["itens"] == []  # curingas removidos
    assert "private" in r.headers["Cache-Control"]


def test_mensagens_anteriores_por_cursor(admin_logado):
    from app.extensions import db
    from app.models import GrupoChat, GrupoMembro, Mensagem, Usuario
    from app.services import chat as svc
    eu = Usuario.query.one()
    g = GrupoChat(nome="G", criador_id=eu.id); db.session.add(g); db.session.flush()
    db.session.add(GrupoMembro(grupo_id=g.id, usuario_id=eu.id, eh_admin=True))
    for i in range(svc.PAGINA * 2 + 5):
        db.session.add(Mensagem(grupo_id=g.id, remetente_id=eu.id, conteudo=f"m{i}"))
    db.session.commit()
    pagina = admin_logado.get(f"/mensagens/{g.id}").get_data(as_text=True)
    assert "data-anteriores" in pagina and "Mensagens anteriores" in pagina and "hidden" not in pagina.split("data-mais")[1][:5]
    ultimo = Mensagem.query.order_by(Mensagem.id.desc()).first().id
    primeiro_visivel = ultimo - svc.PAGINA + 1
    a = admin_logado.get(f"/mensagens/{g.id}/anteriores?antes={primeiro_visivel}").get_json()
    assert len(a["mensagens"]) == svc.PAGINA and a["tem_mais"] is True
    ids = [m["id"] for m in a["mensagens"]]
    assert ids == sorted(ids) and max(ids) == primeiro_visivel - 1  # sem repetir nem pular
    b = admin_logado.get(f"/mensagens/{g.id}/anteriores?antes={a['mensagens'][0]['id']}").get_json()
    assert len(b["mensagens"]) == 5 and b["tem_mais"] is False
    assert admin_logado.get(f"/mensagens/{g.id}/anteriores").status_code == 400
    assert admin_logado.get(f"/mensagens/{g.id}/anteriores?antes=abc").status_code == 400


def test_marcar_lidas_responde_204_para_tela_otimista_e_redireciona_sem_js(client):
    from app.extensions import db
    from app.models import Notificacao, Usuario
    from tests.test_auth import registrar
    registrar(client)
    u = Usuario.query.one()
    db.session.add_all([Notificacao(usuario_id=u.id, tipo="t", titulo="a"), Notificacao(usuario_id=u.id, tipo="t", titulo="b")]); db.session.commit()
    pag = client.get("/notificacoes/").get_data(as_text=True)
    assert "data-otimista" in pag and pag.count("nao-lida") >= 2
    r = client.post("/notificacoes/lidas", headers={"Accept": "application/json"})
    assert r.status_code == 204 and Notificacao.query.filter_by(lida=False).count() == 0
    db.session.add(Notificacao(usuario_id=u.id, tipo="t", titulo="c")); db.session.commit()
    assert client.post("/notificacoes/lidas").status_code == 302  # sem JavaScript: fluxo normal


def test_preload_das_fontes_usa_a_mesma_url_do_font_face(client):
    """Se o preload tiver ?v= e o CSS não, a fonte é baixada duas vezes."""
    import re
    html = client.get("/").data.decode()
    pre = re.findall(r'rel="preload" href="([^"]+\.woff2)[^"]*" as="font"', html)
    assert pre and all("?" not in u for u in pre), pre
    css = client.get(re.search(r'href="(/static/css/tokens\.css[^"]*)"', html).group(1)).data.decode()
    for u in pre:
        assert u.rsplit("/", 1)[1] in css


def test_orcamento_de_fontes(client):
    """Fontes hospedadas aqui, só woff2, font-display: swap e as pré-carregadas somam pouco."""
    import re
    from pathlib import Path
    from app import assets
    css = Path(assets.__file__).parent.joinpath("static/css/tokens.css").read_text()
    assert css.count("@font-face") == css.count("font-display: swap") and "http" not in re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    pasta = Path(assets.__file__).parent / "static/fonts"
    assert {f.suffix for f in pasta.iterdir() if f.is_file()} <= {".woff2", ".md", ".txt"}
    html = client.get("/").data.decode()
    peso = sum((pasta / u.rsplit("/", 1)[1]).stat().st_size for u in re.findall(r'rel="preload" href="([^"]+\.woff2)"', html))
    assert peso <= 100 * 1024, peso


def test_excluir_conta_cancela_email_pendente_na_fila(app, client):
    import json
    from app.extensions import db
    from app.models import Job
    from app.services import jobs, conta
    from tests.test_auth import DADOS, registrar
    from app.models import Usuario
    registrar(client)
    u = Usuario.query.filter_by(email=DADOS["email"]).one()
    app.config["JOBS_MODE"] = "queue"
    jobs.enfileirar("email", {"to": u.email, "subject": "S", "body": "link"}); jobs.enfileirar("email", {"to": "outro@x.com", "subject": "S", "body": "b"})
    db.session.commit()
    conta.excluir(u); db.session.commit()
    assert [json.loads(j.payload_json)["to"] for j in Job.query.all()] == ["outro@x.com"]


def test_rum_recusa_corpo_grande_mesmo_sem_content_length(client):
    corpo = b'{"rota":"main.inicio","m":{"LCP":1},"x":"' + b"a" * 2000 + b'"}'
    import io
    r = client.post("/rum", input_stream=io.BytesIO(corpo), content_type="application/json")  # sem Content-Length
    assert r.status_code == 204
