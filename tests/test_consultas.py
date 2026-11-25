"""Guarda contra N+1: o número de consultas de cada tela NÃO pode crescer com a quantidade de itens exibidos."""
import pytest
from sqlalchemy import event

from app.extensions import db
from app.models import (Alternativa, Amizade, Colecao, ColecaoItem, GrupoChat, GrupoMembro, Materia, Mensagem, Notificacao,
                        Questao, RespostaUsuario, Usuario)
from tests.test_auth import DADOS, registrar


def _popular(eu: Usuario, n: int):
    m = Materia(nome=f"Mat{n}", cor="#112233")
    db.session.add(m); db.session.flush()
    outros = []
    for i in range(n):
        u = Usuario(nome=f"U{i}", sobrenome="X", username=f"u{n}_{i}", email=f"u{n}_{i}@x.com", tag=f"{n:02d}{i:02d}", senha_hash="x", xp=100 + i,
                    icon_path=f"ic{i}.webp")
        db.session.add(u); outros.append(u)
    db.session.flush()
    col = Colecao(usuario_id=eu.id, nome=f"C{n}")
    db.session.add(col); db.session.flush()
    for i in range(n):
        q = Questao(enunciado=f"Enunciado {i}", materia_id=m.id, dificuldade="facil", conteudo="c")
        q.alternativas = [Alternativa(texto="a", correta=True), Alternativa(texto="b")]
        db.session.add(q); db.session.flush()
        db.session.add(ColecaoItem(colecao_id=col.id, questao_id=q.id))
        db.session.add(RespostaUsuario(usuario_id=eu.id, questao_id=q.id, acertou=bool(i % 2)))
        db.session.add(Notificacao(usuario_id=eu.id, tipo="t", titulo=f"N{i}"))
        db.session.add(Amizade(solicitante_id=eu.id, destinatario_id=outros[i].id, status="aceito"))
    g = GrupoChat(nome="Grupo", criador_id=eu.id)
    db.session.add(g); db.session.flush()
    db.session.add(GrupoMembro(grupo_id=g.id, usuario_id=eu.id, eh_admin=True))
    for i in range(n):
        db.session.add(GrupoMembro(grupo_id=g.id, usuario_id=outros[i].id))
        db.session.add(Mensagem(grupo_id=g.id, remetente_id=outros[i].id, conteudo=f"oi {i}"))
    db.session.commit()
    return m, col, g


def _consultas(client, url):
    n = [0]

    def conta(*_a, **_k):
        n[0] += 1
    eng = db.engine
    event.listen(eng, "before_cursor_execute", conta)
    try:
        r = client.get(url)
    finally:
        event.remove(eng, "before_cursor_execute", conta)
    assert r.status_code == 200, (url, r.status_code)
    return n[0]


@pytest.fixture()
def admin(app, client):
    registrar(client)
    u = Usuario.query.filter_by(email=DADOS["email"]).one()
    u.is_admin = True
    db.session.commit()
    return u


def _rotas(m, col, g):
    return ["/", "/ranking/", f"/ranking/?materia_id={m.id}", "/notificacoes/", f"/colecoes/{col.id}", "/colecoes/", "/amigos", "/mensagens",
            f"/mensagens/{g.id}", f"/mensagens/{g.id}/novas?depois=0", "/perfil/ana", "/admin/questoes", "/simulados/", "/loja/", "/missoes/",
            "/competicoes/", "/revisao/"]


def test_consultas_nao_crescem_com_os_dados(client, admin):
    pequeno = _popular(admin, 3)
    antes = {u: _consultas(client, u) for u in _rotas(*pequeno)}
    grande = _popular(admin, 20)
    cresceu = {}
    for u in _rotas(*grande):
        base = u.replace(str(grande[0].id), str(pequeno[0].id)).replace(f"/{grande[1].id}", f"/{pequeno[1].id}").replace(f"/{grande[2].id}", f"/{pequeno[2].id}")
        depois = _consultas(client, u)
        if depois > antes.get(base, depois) + 1:
            cresceu[u] = (antes.get(base), depois)
    assert not cresceu, f"N+1 em: {cresceu}"


def _plano(stmt) -> str:
    from sqlalchemy import text
    sql = str(stmt.compile(db.engine, compile_kwargs={"literal_binds": True}))
    return " | ".join(r[3] for r in db.session.execute(text("EXPLAIN QUERY PLAN " + sql)))


def test_consultas_comuns_usam_indice(app):
    from datetime import datetime
    from sqlalchemy import select, func
    from app.models import Assinatura, Mensagem, Notificacao, Pagamento, RespostaUsuario, RevisaoQuestao, Torneio, Usuario, XpEvento
    agora = datetime(2026, 1, 1)
    casos = {
        "ranking geral": (select(Usuario.id, Usuario.xp).where(Usuario.is_banido.is_(False), Usuario.xp > 0).order_by(Usuario.xp.desc()).limit(15), "ix_usuarios_ranking"),
        "ranking por período": (select(XpEvento.usuario_id, func.sum(XpEvento.valor)).where(XpEvento.criado_em >= agora, XpEvento.valor > 0).group_by(XpEvento.usuario_id), "ix_xp_eventos"),
        "competições vencidas": (select(Torneio.id).where(Torneio.status == "aberto", Torneio.fim <= agora), "ix_torneios_status_fim"),
        "assinaturas vencidas": (select(Assinatura.id).where(Assinatura.status == "ativa", Assinatura.expira < agora), "ix_assinaturas_expira"),
        "pagamentos pendentes": (select(Pagamento.id).where(Pagamento.status.in_(("criado", "pendente")), Pagamento.criado_em <= agora), "ix_pagamentos_status"),
        "cota de imagens do chat": (select(func.count(Mensagem.id)).where(Mensagem.remetente_id == 1, Mensagem.imagem_path.is_not(None), Mensagem.enviado_em > agora), "ix_mensagens_remetente"),
        "não lidas": (select(func.count(Notificacao.id)).where(Notificacao.usuario_id == 1, Notificacao.lida.is_(False)), "ix_notif_usuario"),
        "histórico de respostas": (select(RespostaUsuario.id).where(RespostaUsuario.usuario_id == 1).order_by(RespostaUsuario.data_resposta.desc()).limit(8), "ix_respostas_usuario_data"),
        "revisão devida": (select(RevisaoQuestao.id).where(RevisaoQuestao.usuario_id == 1, RevisaoQuestao.ativo.is_(True), RevisaoQuestao.proxima_em <= agora), "ix_revisao_devida"),
    }
    sem_indice = {k: p for k, (q, idx) in casos.items() if idx not in (p := _plano(q))}
    assert not sem_indice, sem_indice
