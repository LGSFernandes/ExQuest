import json

from app.extensions import db
from app.models import (Alternativa, LancamentoCarteira, Materia, Questao, RespostaUsuario, RevisaoQuestao,
                        SimuladoSessao, Usuario)
from app.services import wallet
from tests.test_auth import registrar


def _banco(n=3):
    m = Materia(nome="Matemática")
    db.session.add(m)
    db.session.flush()
    qs = []
    for i in range(n):
        q = Questao(enunciado=f"Quanto é {i}+1?", materia_id=m.id, dificuldade="facil", explicacao="Some.")
        q.alternativas = [Alternativa(texto="certa", correta=True), Alternativa(texto="errada", correta=False)]
        db.session.add(q)
        qs.append(q)
    db.session.commit()
    return m, qs


def _entrar(client):
    registrar(client)
    return Usuario.query.filter_by(email="ana@exemplo.com").one()


def _resp(client, q, certa=True, **extra):
    alt = next(a for a in q.alternativas if a.correta == certa)
    return client.post("/questoes/responder", json={"questao_id": q.id, "alternativa_id": alt.id, **extra})


def test_recompensa_so_na_primeira_resposta_correta(client, app):
    u = _entrar(client)
    _, qs = _banco(1)
    r1 = _resp(client, qs[0]).get_json()
    assert r1["acertou"] and r1["primeira_vez"] and r1["xp_ganho"] > 0 and r1["moedas_ganhas"] > 0
    r2 = _resp(client, qs[0]).get_json()
    assert r2["acertou"] and not r2["primeira_vez"] and r2["xp_ganho"] == 0 and r2["moedas_ganhas"] == 0
    db.session.refresh(u)
    assert u.xp == r1["xp_ganho"] and u.moedas == r1["moedas_ganhas"]
    assert wallet.conferir(u.id)[0]  # saldo == soma do ledger
    assert LancamentoCarteira.query.filter_by(usuario_id=u.id, categoria="resposta").count() == 1
    assert u.streak.sequencia_atual == 1


def test_erro_vai_para_revisao_e_alternativa_de_outra_questao_e_recusada(client, app):
    u = _entrar(client)
    _, qs = _banco(2)
    r = _resp(client, qs[0], certa=False).get_json()
    assert not r["acertou"] and r["xp_ganho"] == 0
    assert RevisaoQuestao.query.filter_by(usuario_id=u.id, questao_id=qs[0].id).count() == 1
    alheia = qs[1].alternativas[0]
    assert client.post("/questoes/responder", json={"questao_id": qs[0].id, "alternativa_id": alheia.id}).status_code == 400
    assert client.post("/questoes/responder", json={"questao_id": "x"}).status_code == 400


def test_limite_diario_do_plano_gratuito(client, app):
    _entrar(client)
    _, qs = _banco(5)
    codigos = [_resp(client, q).status_code for q in qs]
    assert codigos == [200, 200, 200, 429, 429]  # plano gratuito: 3 por dia
    assert RespostaUsuario.query.count() == 3


def test_questoes_nao_vaza_gabarito_no_html_e_exige_login(client, app):
    assert client.get("/questoes/").status_code == 302
    assert client.post("/questoes/responder", json={}).status_code in (302, 400, 401)
    _entrar(client)
    m, qs = _banco(1)
    html = client.get(f"/questoes/?materia_id={m.id}").data.decode()
    assert "Quanto é 0+1?" in html and 'name="alt"' in html and "correta" not in html.lower().replace("certa", "")
    assert b"style=" not in html.encode()


def test_simulado_ciclo_completo_e_nao_refaz_recompensa(client, app):
    u = _entrar(client)
    m, qs = _banco(3)
    r = client.post("/simulados/iniciar", data={"materia_id": m.id, "quantidade": 3})
    assert r.status_code == 302
    s = SimuladoSessao.query.one()
    assert s.total == 3 and s.limite_segundos == 360
    pagina = client.get(f"/simulados/{s.token}").data.decode()
    assert "Enviar simulado" in pagina
    dados = {}
    for i, qid in enumerate(json.loads(s.questoes_json)):
        q = db.session.get(Questao, qid)
        dados[f"q{qid}"] = next(a for a in q.alternativas if a.correta == (i != 2)).id
    r = client.post(f"/simulados/{s.token}/finalizar", data=dados)
    assert r.status_code == 302
    db.session.refresh(s)
    assert s.status == "finalizado" and s.acertos == 2 and s.xp_total > 0
    assert client.post(f"/simulados/{s.token}/finalizar", data=dados).status_code == 302  # segunda vez não pontua
    assert RespostaUsuario.query.count() == 3
    assert b"2" in client.get(f"/simulados/{s.token}").data
    db.session.refresh(u)
    assert u.xp == s.xp_total and wallet.conferir(u.id)[0]


def test_simulado_de_outro_usuario_da_404_e_limite_de_simulados(client, app):
    _entrar(client)
    m, _ = _banco(2)
    client.post("/simulados/iniciar", data={"materia_id": m.id, "quantidade": 2})
    s = SimuladoSessao.query.one()
    client.post("/sair")
    registrar(client, username="bia", email="bia@exemplo.com")
    assert client.get(f"/simulados/{s.token}").status_code == 404
    assert client.post(f"/simulados/{s.token}/finalizar").status_code == 404
    client.post("/simulados/iniciar", data={"materia_id": m.id, "quantidade": 2})
    client.post("/simulados/iniciar", data={"materia_id": m.id, "quantidade": 2})
    assert SimuladoSessao.query.count() == 2  # plano gratuito: 1 por dia (+ o do outro usuário)


def test_simulado_enviado_fora_do_tempo_nao_rende_recompensa(client, app):
    from datetime import timedelta
    u = _entrar(client)
    m, _ = _banco(1)
    client.post("/simulados/iniciar", data={"materia_id": m.id, "quantidade": 1})
    s = SimuladoSessao.query.one()
    s.iniciado_em = s.iniciado_em - timedelta(hours=2)
    db.session.commit()
    q = db.session.get(Questao, json.loads(s.questoes_json)[0])
    client.post(f"/simulados/{s.token}/finalizar", data={f"q{q.id}": q.alternativa_correta.id})
    db.session.refresh(s)
    assert s.status == "expirado" and s.acertos == 1 and s.xp_total == 0
    db.session.refresh(u)
    assert u.xp == 0


def test_painel_e_ranking_renderizam(client, app):
    _entrar(client)
    m, qs = _banco(1)
    _resp(client, qs[0])
    for url in ("/", "/ranking/", f"/ranking/?materia_id={m.id}&periodo=semana", "/ranking/?periodo=mes", "/simulados/"):
        r = client.get(url)
        assert r.status_code == 200, url
        assert b"style=" not in r.data
    assert client.get("/ranking/?materia_id=999").status_code == 404
    assert b"Matem" in client.get("/").data


def test_discursiva_avalia_e_exige_texto(client, app):
    _entrar(client)
    m, _ = _banco(0)
    q = Questao(enunciado="Explique a fotossíntese", materia_id=m.id, tipo="discursiva",
                resposta_correta="Plantas convertem luz solar, água e gás carbônico em glicose e oxigênio")
    db.session.add(q); db.session.commit()
    assert client.post("/questoes/responder-discursiva", json={"questao_id": q.id, "resposta_texto": " "}).status_code == 400
    ok = client.post("/questoes/responder-discursiva", json={"questao_id": q.id,
        "resposta_texto": "Plantas convertem luz solar, água e gás carbônico em glicose e oxigênio"}).get_json()
    assert ok["acertou"] and ok["nota"] >= 55
    ruim = client.post("/questoes/responder-discursiva", json={"questao_id": q.id, "resposta_texto": "não sei nada sobre isso"}).get_json()
    assert not ruim["acertou"]


def test_revisao_erro_volta_acerto_espaca_e_nao_gasta_limite(client, app):
    from datetime import timedelta
    from app import clock
    u = _entrar(client)
    _, qs = _banco(1)
    _resp(client, qs[0], certa=False)
    assert b"nada para revisar" in client.get("/revisao/").data.lower()  # só amanhã
    r = RevisaoQuestao.query.one()
    r.proxima_em = clock.agora() - timedelta(minutes=1); db.session.commit()
    html = client.get("/revisao/").data.decode()
    assert "Quanto é 0+1?" in html and 'name="alt"' in html
    antes = Usuario.query.one().questoes_hoje
    alt = next(a for a in qs[0].alternativas if a.correta)
    j = client.post("/revisao/responder", json={"questao_id": qs[0].id, "alternativa_id": alt.id}).get_json()
    assert j["acertou"] and j["primeira_vez"]  # 1º acerto da questão rende; a revisão em si não
    db.session.refresh(r)
    assert r.repeticoes == 1 and r.intervalo_dias == 1 and r.proxima_em > clock.agora()
    assert Usuario.query.one().questoes_hoje == antes  # revisão não consome o limite diário
    assert client.post("/revisao/responder", json={"questao_id": qs[0].id, "alternativa_id": 99999}).status_code == 400
    qs[0].ativo = False; db.session.commit()  # questão desativada pelo admin não é mais respondida nem na revisão
    assert client.post("/revisao/responder", json={"questao_id": qs[0].id, "alternativa_id": alt.id}).status_code == 400


def test_subir_de_nivel_gera_uma_notificacao(client, app):
    from app.models import Notificacao
    from app.services import niveis
    u = _entrar(client)
    _, qs = _banco(2)
    u.xp = niveis.xp_inicio_do_nivel(u.nivel + 1) - 1  # falta 1 XP para o próximo nível
    db.session.commit()
    nivel_antes = u.nivel
    assert _resp(client, qs[0]).status_code == 200
    db.session.refresh(u)
    assert u.nivel == nivel_antes + 1
    assert [n.titulo for n in Notificacao.query.filter_by(tipo="nivel")] == [f"Você subiu para o nível {u.nivel}"]
    _resp(client, qs[0])  # repetir a mesma questão não rende XP nem aviso
    assert Notificacao.query.filter_by(tipo="nivel").count() == 1


def test_pagina_premium_abre_para_admin_sem_plano_e_para_aluno_com_plano(client):
    from datetime import timedelta
    from app import clock
    from app.extensions import db
    from app.models import Usuario
    from tests.test_auth import registrar
    registrar(client)
    u = Usuario.query.one()
    assert client.get("/premium").status_code == 200
    u.is_admin = True; db.session.commit()
    r = client.get("/premium")
    assert r.status_code == 200 and "sem prazo de validade" in r.data.decode()
    u.is_admin, u.plano_premium, u.premium_expira = False, "inter", clock.agora() + timedelta(days=3); db.session.commit()
    assert "ativo até" in client.get("/premium").data.decode()


def test_buscar_sem_materia_explica_o_que_falta(client):
    from tests.test_auth import registrar
    registrar(client)
    r = client.get("/questoes/?sessao_id=abc&tipo=&conteudo=")
    assert "Escolha ao menos uma matéria" in r.data.decode()
    assert "Escolha ao menos uma matéria" not in client.get("/questoes/").data.decode()


def test_resumo_de_enunciado_nao_corta_formula_nem_mostra_latex(app):
    f = app.jinja_env.filters["resumo"]
    r = f(r"Calcule $\frac{1}{2} + x^2$ quando x vale 3 e depois some tudo isso ao resultado final da conta", 40)
    assert "$" not in r and "\\" not in r and r.endswith("…") and len(r) <= 41
    assert f("curto") == "curto"
