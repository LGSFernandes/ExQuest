"""Direitos do titular (LGPD): exportar os dados da conta e excluí-la.

Exclusão = anonimização. A linha do usuário permanece (o histórico financeiro e de pagamentos precisa ser guardado
por obrigação legal e o ranking/competições passadas dependem dela), mas perde tudo que identifica a pessoa:
nome, e-mail, usuário, senha, foto, banner, bio, vínculos sociais, mensagens e coleções."""
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from app import clock
from app.extensions import db
from app.models import (Amizade, Bloqueio, Colecao, GrupoMembro, InventarioItem, LancamentoCarteira, Mensagem, Notificacao, Pagamento,
                        RespostaUsuario, RevisaoQuestao, SimuladoSessao, TokenRecuperacao, Usuario, LogAuditoria, MissaoProgresso, TorneioParticipante, Denuncia, TorneioResposta)
from app.services import amizades, uploads


class ErroConta(Exception):
    pass


def _iso(d):
    return d.isoformat() if d else None


def exportar(u: Usuario) -> dict:
    """Tudo que o próprio titular enviou ou gerou. Não inclui senha, tokens nem dados de outras pessoas."""
    colecoes = [{"nome": c.nome, "questoes": [i.questao_id for i in c.itens]} for c in Colecao.query.filter_by(usuario_id=u.id)]
    return {
        "gerado_em": _iso(clock.agora()),
        "conta": {"nome": u.nome, "sobrenome": u.sobrenome, "usuario": u.username, "tag": u.tag, "email": u.email, "biografia": u.biografia,
                  "xp": u.xp, "moedas": u.moedas, "plano": u.plano_premium, "premium_expira": _iso(u.premium_expira), "perfil_publico": u.perfil_publico,
                  "login_google": bool(u.google_id)},
        "respostas": [{"questao_id": r.questao_id, "acertou": r.acertou, "em": _iso(r.data_resposta)} for r in RespostaUsuario.query.filter_by(usuario_id=u.id)],
        "carteira": [{"tipo": x.tipo, "valor": x.valor, "categoria": x.categoria, "descricao": x.descricao, "em": _iso(x.criado_em)} for x in LancamentoCarteira.query.filter_by(usuario_id=u.id)],
        "pagamentos": [{"id": p.id, "provedor": p.provider, "tipo": p.tipo, "descricao": p.descricao, "valor_centavos": p.valor_centavos, "status": p.status, "em": _iso(p.criado_em)}
                       for p in Pagamento.query.filter_by(usuario_id=u.id)],
        "colecoes": colecoes,
        "mensagens_enviadas": [{"grupo_id": m.grupo_id, "texto": m.conteudo, "em": _iso(m.enviado_em)}
                               for m in Mensagem.query.filter_by(remetente_id=u.id, deletado=False)],
        "notificacoes": [{"titulo": n.titulo, "corpo": n.corpo, "em": _iso(n.criado_em)} for n in Notificacao.query.filter_by(usuario_id=u.id)],
        "inventario": [i.item_id for i in InventarioItem.query.filter_by(usuario_id=u.id)],
        "sequencia": {"atual": u.streak.sequencia_atual, "maior": u.streak.maior_sequencia, "ultima_atividade": _iso(u.streak.ultima_atividade),
                      "escudos": u.streak.escudos} if u.streak else None,
        "simulados": [{"inicio": _iso(s.iniciado_em), "fim": _iso(s.finalizado_em), "status": s.status, "acertos": s.acertos, "total": s.total,
                       "xp": s.xp_total, "moedas": s.moedas_total} for s in SimuladoSessao.query.filter_by(usuario_id=u.id)],
        "revisao": [{"questao_id": r.questao_id, "proxima_em": _iso(r.proxima_em), "lapsos": r.lapsos, "origem": r.origem}
                    for r in RevisaoQuestao.query.filter_by(usuario_id=u.id)],
        "missoes": [{"missao": m.missao_slug, "periodo": m.periodo_chave, "progresso": m.progresso, "meta": m.meta,
                     "concluida_em": _iso(m.concluida_em), "resgatada_em": _iso(m.resgatada_em)} for m in MissaoProgresso.query.filter_by(usuario_id=u.id)],
        "competicoes": [{"competicao": p.torneio.nome, "pontos": p.pontuacao, "acertos": p.acertos, "posicao": p.posicao, "entrou_em": _iso(p.entrou_em)}
                        for p in TorneioParticipante.query.filter_by(usuario_id=u.id)],
        "respostas_discursivas": [{"questao_id": r.questao_id, "texto": r.resposta_texto} for r in RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id == u.id, RespostaUsuario.resposta_texto.isnot(None))]
        + [{"competicao_questao_id": r.questao_id, "texto": r.resposta_texto} for r in TorneioResposta.query.filter(
            TorneioResposta.participante_id.in_(select(TorneioParticipante.id).where(TorneioParticipante.usuario_id == u.id)),
            TorneioResposta.resposta_texto.isnot(None))],
        "denuncias_enviadas": [{"tipo": d.alvo_tipo, "motivo": d.motivo, "detalhe": d.detalhe} for d in Denuncia.query.filter_by(autor_id=u.id)],
        "amigos": [{"usuario": a.username} for a in amizades.amigos(u.id)],
        "bloqueados": [db.session.get(Usuario, b.bloqueado_id).username for b in Bloqueio.query.filter_by(bloqueador_id=u.id)],
        "registro_de_seguranca": [{"acao": l.acao, "ip": l.ip, "navegador": l.user_agent, "em": _iso(l.criado_em)} for l in LogAuditoria.query.filter_by(usuario_id=u.id)],
    }


def _cancelar_jobs_pendentes(email: str) -> None:
    """E-mails ainda na fila para o endereço antigo não podem sair depois da anonimização (e o payload deixa de existir)."""
    from app.models import Job
    Job.query.filter(Job.status == "pendente", Job.payload_json.contains(email)).delete(synchronize_session=False)


def excluir(u: Usuario) -> None:
    if u.is_admin:
        raise ErroConta("Contas de administrador não podem ser excluídas por aqui. Peça a outro administrador para remover o acesso antes.")
    recente = clock.agora() - timedelta(days=1)
    pendente = Pagamento.query.filter(Pagamento.usuario_id == u.id, or_(Pagamento.status == "pendente", (Pagamento.status == "criado") & (Pagamento.criado_em > recente))).first()
    if pendente:
        raise ErroConta("Há um pagamento pendente nesta conta. Aguarde a confirmação ou o cancelamento e tente de novo.")
    uid = u.id
    _cancelar_jobs_pendentes(u.email)
    for n in Notificacao.query.filter(Notificacao.usuario_id != uid, Notificacao.origem_id == uid):  # avisos de outras pessoas citam o nome
        n.corpo = "Uma conta excluída enviou este aviso."
    for n in Notificacao.query.filter(Notificacao.usuario_id != uid, Notificacao.origem_id.is_(None), Notificacao.tipo.in_(("amizade", "chat")),
                                      Notificacao.corpo.startswith(f"{u.nome} ", autoescape=True)):  # avisos antigos, sem remetente gravado
        n.corpo = "Uma conta excluída " + n.corpo[len(u.nome) + 1:]
    db.session.execute(update(RespostaUsuario).where(RespostaUsuario.usuario_id == uid).values(resposta_texto=None))  # texto livre da pessoa
    db.session.execute(update(TorneioResposta).where(TorneioResposta.participante_id.in_(select(TorneioParticipante.id).where(TorneioParticipante.usuario_id == uid))).values(resposta_texto=None))
    db.session.execute(update(Denuncia).where(Denuncia.autor_id == uid).values(detalhe=None))
    for m in Mensagem.query.filter_by(remetente_id=uid):
        if m.imagem_path:
            uploads.remover_apos_commit("chat", m.imagem_path, privado=True)
        m.conteudo, m.imagem_path, m.deletado = None, None, True
    uploads.remover_apos_commit("icon", u.icon_path)
    uploads.remover_apos_commit("banner", u.banner_path)
    for gm in GrupoMembro.query.filter_by(usuario_id=uid).all():  # grupo nunca fica sem administrador nem vazio
        g = gm.grupo
        restantes = [m for m in g.membros.order_by(GrupoMembro.entrou_em) if m.usuario_id != uid]
        if not restantes and not g.is_direto:
            for msg in g.mensagens:
                uploads.remover_apos_commit("chat", msg.imagem_path, privado=True)
            db.session.delete(g)
        elif gm.eh_admin and not g.is_direto and not any(m.eh_admin for m in restantes):
            restantes[0].eh_admin = True
    db.session.flush()
    for c in Colecao.query.filter_by(usuario_id=uid):
        db.session.delete(c)
    for modelo, cond in ((Amizade, or_(Amizade.solicitante_id == uid, Amizade.destinatario_id == uid)),
                         (Bloqueio, or_(Bloqueio.bloqueador_id == uid, Bloqueio.bloqueado_id == uid)),
                         (GrupoMembro, GrupoMembro.usuario_id == uid), (Notificacao, Notificacao.usuario_id == uid),
                         (TokenRecuperacao, TokenRecuperacao.usuario_id == uid), (InventarioItem, InventarioItem.usuario_id == uid),
                         (RevisaoQuestao, RevisaoQuestao.usuario_id == uid), (SimuladoSessao, SimuladoSessao.usuario_id == uid)):
        db.session.execute(delete(modelo).where(cond))
    db.session.execute(update(LogAuditoria).where(LogAuditoria.usuario_id == uid).values(ip=None, user_agent=None))  # mantém o histórico de ações, sem identificar o aparelho
    u.nome, u.sobrenome, u.username = "Conta", "excluída", f"excluido-{uid}"  # hífen não passa em validar_username: nunca colide com um cadastro real
    u.email, u.senha_hash, u.google_id, u.tag_custom = f"excluido-{uid}@exquest.invalid", None, None, None
    u.icon_path = u.banner_path = None
    u.biografia = ""
    u.perfil_publico = False
    u.plano_premium = u.premium_expira = u.premium_ciclo = u.premium_cancelar_em = None
    u.is_banido = True  # impede qualquer sessão restante de voltar a funcionar
    u.session_version = (u.session_version or 0) + 1
