import json
from datetime import timedelta

import pytest

from app import clock
from app.extensions import db
from app.models import Alternativa, Materia, Questao, Torneio, TorneioParticipante, Usuario
from app.models import LancamentoCarteira
from app.services import competicoes as svc
from tests.test_auth import registrar


_seq = [0]


def _alunos(n, plano="inter"):
    us = []
    for _ in range(n):
        _seq[0] += 1
        i = _seq[0]
        u = Usuario(username=f"u{i}", email=f"u{i}@x.com", nome=f"U{i}", sobrenome="X", tag=f"{i:04d}", senha_hash="x",
                    plano_premium=plano, premium_expira=clock.agora() + timedelta(days=30))
        db.session.add(u); us.append(u)
    db.session.flush()
    return us


def _torneio(qtd=5, inicio=None, fim=None):
    m = Materia(nome="M"); db.session.add(m); db.session.flush()
    for i in range(qtd):
        q = Questao(materia_id=m.id, enunciado=f"Q{i}", tipo="multipla", dificuldade="facil", ativo=True)
        db.session.add(q); db.session.flush()
        db.session.add_all([Alternativa(questao_id=q.id, texto="certa", correta=True), Alternativa(questao_id=q.id, texto="errada", correta=False)])
    agora = clock.agora()
    t = svc.criar(nome="Copa", descricao=None, tipo="micro", materias=[], dificuldades=[],
                  inicio=inicio or agora - timedelta(minutes=5), fim=fim or agora + timedelta(hours=2))
    db.session.commit()
    return t


def _respostas(t, certas):
    out = {}
    for i, q in enumerate(svc.questoes(t)):
        alt = next(a for a in q.alternativas if a.correta == (i < certas))
        out[q.id] = alt.id
    return out


def test_criar_exige_questoes_suficientes_e_janela_valida(app):
    _torneio(5)
    agora = clock.agora()
    with pytest.raises(svc.ErroCompeticao):
        svc.criar(nome="X", descricao=None, tipo="pequeno", materias=[], dificuldades=[], inicio=agora, fim=agora + timedelta(hours=1))
    with pytest.raises(svc.ErroCompeticao):
        svc.criar(nome="X", descricao=None, tipo="micro", materias=[], dificuldades=[], inicio=agora, fim=agora + timedelta(minutes=3))


def test_plano_gratuito_nao_entra_e_limite_mensal(app):
    (free,) = _alunos(1, plano=None)
    t = _torneio()
    with pytest.raises(svc.ErroCompeticao):
        svc.entrar(free, t)
    (u,) = _alunos(1)  # intermediário: 3 por mês
    assert svc.entrar(u, t).id == svc.entrar(u, t).id  # idempotente
    for i in range(2):  # com a 1ª já são 3
        svc.entrar(u, _t_extra(i))
    db.session.commit()
    assert svc.mes_usado(u.id) == 3
    with pytest.raises(svc.ErroCompeticao):
        svc.entrar(u, _t_extra(9))


def _t_extra(i):
    agora = clock.agora()
    t = Torneio(nome=f"Extra{i}", tipo="micro", inicio=agora - timedelta(minutes=1), fim=agora + timedelta(hours=1), num_questoes=5, tempo_minutos=10)
    db.session.add(t); db.session.flush()
    return t


def test_relogio_nao_reinicia_e_envio_unico(app):
    t = _torneio()
    (u,) = _alunos(1)
    svc.entrar(u, t); p = svc.comecar(u, t)
    ini = p.iniciou_em
    assert svc.comecar(u, t).iniciou_em == ini
    p = svc.enviar(u, t, _respostas(t, 3))
    assert (p.acertos, p.pontuacao, p.finalizado) == (3, 300, True)
    with pytest.raises(svc.ErroCompeticao):
        svc.enviar(u, t, _respostas(t, 5))  # segundo envio não troca a nota
    assert svc.meu(t, u.id).pontuacao == 300


def test_envio_atrasado_vale_zero_e_alternativa_de_outra_questao_e_ignorada(app):
    t = _torneio()
    a, b = _alunos(2)
    for u in (a, b):
        svc.entrar(u, t); svc.comecar(u, t)
    svc.meu(t, a.id).iniciou_em = clock.agora() - timedelta(minutes=t.tempo_minutos + 5)
    db.session.commit()
    assert svc.enviar(a, t, _respostas(t, 5)).pontuacao == 0
    qs = svc.questoes(t)
    cruzada = {qs[0].id: qs[1].alternativas[0].id}  # alternativa que pertence a outra questão
    p = svc.enviar(b, t, cruzada)
    assert (p.respondidas, p.acertos) == (0, 0)


def test_encerrar_ordena_por_acertos_depois_tempo_e_paga_uma_vez(app):
    t = _torneio()
    a, b, c, d = _alunos(4)
    ps = {}
    for u in (a, b, c, d):
        svc.entrar(u, t); ps[u.id] = svc.comecar(u, t)
    base = clock.agora()
    # a e b empatam em 4 acertos; b termina mais rápido. c faz 2. d não envia.
    svc.enviar(a, t, _respostas(t, 4)); svc.enviar(b, t, _respostas(t, 4)); svc.enviar(c, t, _respostas(t, 2))
    ps[a.id].iniciou_em, ps[a.id].terminou_em = base, base + timedelta(minutes=8)
    ps[b.id].iniciou_em, ps[b.id].terminou_em = base, base + timedelta(minutes=5)
    db.session.commit()
    xp_antes = {u.id: u.xp or 0 for u in (a, b, c, d)}
    assert svc.encerrar(t) is True
    db.session.commit()
    assert svc.encerrar(t) is False  # segunda chamada não paga de novo
    pos = {p.usuario_id: p.posicao for p in svc.participantes(t)}
    assert (pos[b.id], pos[a.id], pos[c.id], pos[d.id]) == (1, 2, 3, 4)
    assert db.session.get(Usuario, b.id).xp - xp_antes[b.id] == t.recompensa_xp_1
    assert db.session.get(Usuario, a.id).moedas == t.recompensa_moedas_2
    assert db.session.get(Usuario, d.id).moedas in (0, None)  # 0 ponto não ganha prêmio
    assert LancamentoCarteira.query.filter_by(categoria="torneio").count() == 3
    assert t.status == "finalizado"


def test_encerrar_vencidos_so_apos_o_fim(app):
    t = _torneio()
    assert svc.encerrar_vencidos() == 0
    t.fim = clock.agora() - timedelta(minutes=5); t.inicio = t.fim - timedelta(hours=1)
    db.session.commit()
    assert svc.encerrar_vencidos() == 1 and svc.encerrar_vencidos() == 0


def test_cancelar_nao_paga(app):
    t = _torneio()
    (u,) = _alunos(1)
    svc.entrar(u, t); svc.comecar(u, t); svc.enviar(u, t, _respostas(t, 5))
    svc.cancelar(t); db.session.commit()
    assert svc.encerrar(t) is False and LancamentoCarteira.query.filter_by(categoria="torneio").count() == 0


def test_fluxo_web_gabarito_oculto_e_regras(client, app):
    registrar(client)
    u = Usuario.query.one()
    u.plano_premium, u.premium_expira = "inter", clock.agora() + timedelta(days=5)
    t = _torneio()
    db.session.commit()
    assert client.get("/competicoes/").status_code == 200
    assert client.post(f"/competicoes/{t.id}/comecar").status_code == 302  # sem inscrição: volta com aviso
    client.post(f"/competicoes/{t.id}/entrar")
    r = client.post(f"/competicoes/{t.id}/comecar", follow_redirects=True)
    html = r.data.decode()
    assert "Enviar prova" in html and 'data-restante="' in html
    certa_id = Alternativa.query.filter_by(correta=True).first().id
    assert f'value="{certa_id}"' in html and "correta" not in html.lower().replace("corretas", "")  # gabarito não vaza
    form = {f"q{q.id}": next(a.id for a in q.alternativas if a.correta) for q in svc.questoes(t)}
    assert client.post(f"/competicoes/{t.id}/enviar", data=form).status_code == 302
    assert client.get(f"/competicoes/{t.id}/jogar").status_code == 302  # já enviou
    assert client.post(f"/competicoes/{t.id}/enviar", data=form).status_code == 302
    assert TorneioParticipante.query.one().pontuacao == 500
    assert client.get("/competicoes/99999").status_code == 404


def test_admin_cria_e_cancela_so_admin(client, app):
    registrar(client)
    u = Usuario.query.one()
    _torneio(5)
    dados = {"nome": "Copa Web", "tipo": "micro", "inicio": "2030-01-01T10:00", "fim": "2030-01-01T14:00"}
    assert client.post("/admin/competicoes/nova", data=dados).status_code == 403
    u.is_admin = True; db.session.commit()
    assert client.get("/admin/competicoes").status_code == 200
    assert client.post("/admin/competicoes/nova", data=dados).status_code == 302
    t = Torneio.query.filter_by(nome="Copa Web").one()
    assert t.inicio.hour == 13  # 10h de Brasília = 13h UTC
    assert client.post("/admin/competicoes/nova", data={**dados, "nome": "Ruim", "fim": "2030-01-01T09:00"}).status_code == 302
    assert Torneio.query.filter_by(nome="Ruim").count() == 0
    client.post(f"/admin/competicoes/{t.id}/cancelar")
    assert db.session.get(Torneio, t.id).status == "cancelado"


def test_manutencao_leve_fecha_competicao_sem_abrir_a_pagina_dela(client, app):
    from app import hooks
    t = _torneio()
    t.fim = clock.agora() - timedelta(minutes=5); t.inicio = t.fim - timedelta(hours=1)
    db.session.commit()
    app.config["TESTING"] = False
    hooks._ULTIMA_MANUTENCAO[0] = float("-inf")
    try:
        client.get("/")  # qualquer página, não a da competição
    finally:
        app.config["TESTING"] = True
    assert db.session.get(Torneio, t.id).status == "finalizado"


def test_entrada_concorrente_devolve_a_existente_sem_erro_500(app, monkeypatch):
    (u,) = _alunos(1)
    t = _torneio()
    existente = svc.entrar(u, t); db.session.commit()
    original, chamadas = svc.meu, []
    def meu_atrasado(tt, uid):  # a 1ª checagem ainda não vê a entrada feita pela outra aba
        chamadas.append(1)
        return None if len(chamadas) == 1 else original(tt, uid)
    monkeypatch.setattr(svc, "meu", meu_atrasado)
    assert svc.entrar(u, t).id == existente.id
    assert TorneioParticipante.query.filter_by(torneio_id=t.id, usuario_id=u.id).count() == 1


def test_revisao_nao_responde_questao_de_competicao_aberta(client, app):
    from app.models import RevisaoQuestao
    registrar(client)
    u = Usuario.query.one()
    u.plano_premium, u.premium_expira = "inter", clock.agora() + timedelta(days=5)
    t = _torneio(); svc.entrar(u, t); db.session.commit()
    q = svc.questoes(t)[0]
    db.session.add(RevisaoQuestao(usuario_id=u.id, questao_id=q.id, proxima_em=clock.agora())); db.session.commit()
    r = client.post("/revisao/responder", json={"questao_id": q.id, "alternativa_id": q.alternativas[0].id})
    assert r.status_code == 403 and b"alternativa_correta_id" not in r.data


def test_gabarito_continua_bloqueado_depois_do_proprio_envio_ate_a_competicao_acabar(app):
    t = _torneio()
    (u,) = _alunos(1)
    svc.entrar(u, t); svc.comecar(u, t); svc.enviar(u, t, _respostas(t, 3)); db.session.commit()
    assert set(svc.ids_bloqueados(u.id)) == {q.id for q in svc.questoes(t)}
    svc.encerrar(t); db.session.commit()
    assert svc.ids_bloqueados(u.id) == []


def test_resultado_de_simulado_nao_mostra_gabarito_de_questao_de_competicao(client, app):
    from app.models import SimuladoSessao
    registrar(client)
    u = Usuario.query.one()
    u.plano_premium, u.premium_expira = "inter", clock.agora() + timedelta(days=5)
    t = _torneio(); qs = svc.questoes(t)
    s = SimuladoSessao(usuario_id=u.id, token="tok-x", questoes_json=json.dumps([qs[0].id]), status="finalizado", limite_segundos=600,
                       iniciado_em=clock.agora(), total=1)
    db.session.add(s); svc.entrar(u, t); db.session.commit()
    html = client.get("/simulados/tok-x").data.decode()
    assert "aparece quando a competição em andamento terminar" in html and 'opcao certa' not in html


def test_simulado_criado_antes_da_inscricao_nao_corrige_questao_de_competicao(client, app):
    """Achado hunter-05: finalizar não consultava o bloqueio e o resultado virava oráculo de gabarito."""
    from app.models import RespostaUsuario, SimuladoSessao
    registrar(client)
    u = Usuario.query.one()
    u.plano_premium, u.premium_expira = "inter", clock.agora() + timedelta(days=5)
    t = _torneio(); qs = svc.questoes(t)
    s = SimuladoSessao(usuario_id=u.id, token="tok-y", questoes_json=json.dumps([qs[0].id]), status="em_andamento", limite_segundos=600,
                       iniciado_em=clock.agora(), total=1)
    db.session.add(s); svc.entrar(u, t); db.session.commit()  # inscrição DEPOIS de criar o simulado
    certa = next(a for a in qs[0].alternativas if a.correta)
    client.post("/simulados/tok-y/finalizar", data={f"q{qs[0].id}": certa.id})
    assert RespostaUsuario.query.count() == 0 and Usuario.query.one().xp == 0
    html = client.get("/simulados/tok-y").data.decode()
    assert "Correta" not in html and "Incorreta" not in html
