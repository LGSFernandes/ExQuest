"""Competições (torneios). O servidor decide tudo: questões fixas, relógio, nota, ranking e prêmios.

Regras:
    - Participar exige plano com `competicoes` e vaga no limite mensal `torneios_mes`.
    - Cada participante tem UM envio. Pontos = 100 por acerto; desempate pelo menor tempo e, depois, por quem entrou primeiro.
    - Envio depois do prazo (+ tolerância) não pontua. O gabarito só aparece depois que a competição encerra.
    - Prêmios (XP e moedas) para o top 3 com pontuação > 0, pagos uma única vez (chaves idempotentes)."""
import json
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app import clock
from app.extensions import db
from app.models import Alternativa, Materia, Questao, Torneio, TorneioParticipante, TorneioQuestao, TorneioResposta, Usuario
from app.models.competition import TORNEIO_CONFIG
from app.services import notificacoes, wallet, xp

TOLERANCIA = timedelta(seconds=30)
PONTOS_POR_ACERTO = 100


class ErroCompeticao(Exception):
    pass


# ---------- criação (admin) ----------
def criar(*, nome: str, descricao: str | None, tipo: str, materias: list[int], dificuldades: list[str], inicio: datetime,
          fim: datetime, premios: dict | None = None) -> Torneio:
    cfg = TORNEIO_CONFIG.get(tipo)
    if cfg is None:
        raise ErroCompeticao("Tipo de competição inválido.")
    if not nome.strip():
        raise ErroCompeticao("Dê um nome à competição.")
    if fim <= inicio:
        raise ErroCompeticao("O fim precisa ser depois do início.")
    if fim - inicio < timedelta(minutes=cfg["tempo_min"]):
        raise ErroCompeticao(f"A janela precisa ter ao menos {cfg['tempo_min']} minutos (o tempo de prova).")
    q = select(Questao.id).join(Materia).where(Questao.ativo.is_(True), Materia.ativo.is_(True), Questao.tipo != "discursiva")
    if materias:
        q = q.where(Questao.materia_id.in_(materias))
    if dificuldades:
        q = q.where(Questao.dificuldade.in_(dificuldades))
    sorteadas = db.session.scalars(q.order_by(func.random()).limit(cfg["questoes"])).all()
    if len(sorteadas) < cfg["questoes"]:
        raise ErroCompeticao(f"Só há {len(sorteadas)} questões de múltipla escolha com esses filtros; este tipo precisa de {cfg['questoes']}.")
    t = Torneio(nome=nome.strip()[:100], descricao=(descricao or "").strip()[:1000] or None, tipo=tipo, materias_json=json.dumps(materias),
                dificuldades_json=json.dumps(dificuldades), num_questoes=cfg["questoes"], tempo_minutos=cfg["tempo_min"], inicio=inicio, fim=fim)
    for k, v in (premios or {}).items():
        if hasattr(t, k) and isinstance(v, int) and 0 <= v <= 1_000_000:
            setattr(t, k, v)
    db.session.add(t)
    db.session.flush()
    for i, qid in enumerate(sorteadas, 1):
        db.session.add(TorneioQuestao(torneio_id=t.id, questao_id=qid, ordem=i))
    return t


def cancelar(t: Torneio) -> None:
    if t.status != "aberto":
        raise ErroCompeticao("Só competições abertas podem ser canceladas.")
    t.status = "cancelado"
    t.finalizado_em = clock.agora()
    for p in participantes(t):
        notificacoes.criar(p.usuario_id, "competicao", "Competição cancelada", t.nome, f"/competicoes/{t.id}")


# ---------- consulta ----------
def ids_bloqueados(uid: int) -> list[int]:
    """Questões de competições abertas em que o aluno está inscrito: não podem ser respondidas, sorteadas nem ter o
    gabarito exibido pelos modos de estudo até a competição terminar (inclusive após o envio dele: outro jogador
    ainda pode estar competindo e receber o gabarito de um colega)."""
    return list(db.session.scalars(select(TorneioQuestao.questao_id).join(Torneio, Torneio.id == TorneioQuestao.torneio_id).join(
        TorneioParticipante, TorneioParticipante.torneio_id == Torneio.id).where(
        Torneio.status == "aberto", TorneioParticipante.usuario_id == uid)))



def questoes(t: Torneio) -> list[Questao]:
    ids = db.session.scalars(select(TorneioQuestao.questao_id).where(TorneioQuestao.torneio_id == t.id).order_by(TorneioQuestao.ordem)).all()
    por_id = {q.id: q for q in db.session.scalars(select(Questao).where(Questao.id.in_(ids)))}
    return [por_id[i] for i in ids if i in por_id]


def participantes(t: Torneio) -> list[TorneioParticipante]:
    return list(db.session.scalars(select(TorneioParticipante).where(TorneioParticipante.torneio_id == t.id)))


def meu(t: Torneio, uid: int) -> TorneioParticipante | None:
    return db.session.scalar(select(TorneioParticipante).where(TorneioParticipante.torneio_id == t.id, TorneioParticipante.usuario_id == uid))


def tempo_gasto(p: TorneioParticipante) -> float:
    if p.iniciou_em and p.terminou_em:
        return max(0.0, (p.terminou_em - p.iniciou_em).total_seconds())
    return float("inf")


def _chave(p: TorneioParticipante):
    return (-(p.pontuacao or 0), tempo_gasto(p), p.entrou_em or datetime.max, p.id)


def ranking(t: Torneio) -> list[TorneioParticipante]:
    """Só quem já terminou a prova entra no ranking."""
    return sorted([p for p in participantes(t) if p.finalizado], key=_chave)


def prazo(t: Torneio, p: TorneioParticipante) -> datetime:
    return min(p.iniciou_em + timedelta(minutes=t.tempo_minutos), t.fim)


def mes_usado(uid: int) -> int:
    hoje = clock.hoje()
    ini = clock.inicio_do_dia_utc(hoje.replace(day=1))
    return db.session.scalar(select(func.count()).select_from(TorneioParticipante).join(Torneio).where(
        TorneioParticipante.usuario_id == uid, TorneioParticipante.entrou_em >= ini, Torneio.status != "cancelado")) or 0


def pode_entrar(u: Usuario, t: Torneio) -> str | None:
    """Motivo (texto para o aluno) pelo qual NÃO pode entrar, ou None."""
    if meu(t, u.id):
        return None
    if t.status != "aberto" or clock.agora() >= t.fim:
        return "Esta competição não está aberta para novas entradas."
    if not u.pode("competicoes"):
        return "Competições estão disponíveis a partir do plano Intermediário."
    teto = u.limite("torneios_mes")
    if teto is not None and mes_usado(u.id) >= teto:
        return f"Você já usou as {teto} participações do mês no seu plano."
    return None


# ---------- participação ----------
def entrar(u: Usuario, t: Torneio) -> TorneioParticipante:
    p = meu(t, u.id)
    if p:
        return p
    motivo = pode_entrar(u, t)
    if motivo:
        raise ErroCompeticao(motivo)
    p = TorneioParticipante(torneio_id=t.id, usuario_id=u.id)
    try:
        with db.session.begin_nested():
            db.session.add(p)
            db.session.flush()
    except IntegrityError:  # duplo clique / duas abas: a entrada já existe (índice único)
        return meu(t, u.id)
    teto = u.limite("torneios_mes")
    if teto is not None and mes_usado(u.id) > teto:  # corrida entre duas competições no mesmo instante
        with db.session.begin_nested():
            db.session.delete(p)
        raise ErroCompeticao(f"Você já usou as {teto} participações do mês no seu plano.")
    return p


def comecar(u: Usuario, t: Torneio) -> TorneioParticipante:
    p = meu(t, u.id)
    agora = clock.agora()
    if p is None:
        raise ErroCompeticao("Entre na competição primeiro.")
    if p.iniciou_em:
        return p  # recarregar a página não reinicia o relógio
    if t.status != "aberto" or agora < t.inicio:
        raise ErroCompeticao("A competição ainda não começou." if agora < t.inicio else "A competição foi encerrada.")
    if agora >= t.fim:
        raise ErroCompeticao("A competição foi encerrada.")
    db.session.execute(update(TorneioParticipante).where(TorneioParticipante.id == p.id, TorneioParticipante.iniciou_em.is_(None))
                            .values(iniciou_em=agora))
    db.session.refresh(p)
    return p


def enviar(u: Usuario, t: Torneio, respostas: dict[int, int]) -> TorneioParticipante:
    """`respostas`: questao_id -> alternativa_id. Um único envio; o que estiver em branco conta como erro."""
    p = meu(t, u.id)
    if p is None or not p.iniciou_em:
        raise ErroCompeticao("Você ainda não começou a prova.")
    # reivindica o envio de forma atômica: dois cliques ou duas abas não pontuam duas vezes
    agora = clock.agora()
    limite = prazo(t, p)
    atrasado = agora > limite + TOLERANCIA
    reivindicou = db.session.execute(update(TorneioParticipante).where(TorneioParticipante.id == p.id, TorneioParticipante.finalizado.is_(False))
                                     .values(finalizado=True, terminou_em=min(agora, limite))).rowcount
    if not reivindicou:
        raise ErroCompeticao("Você já enviou esta prova.")
    acertos = respondidas = 0
    for q in questoes(t):
        aid = respostas.get(q.id)
        alt = db.session.get(Alternativa, aid) if aid else None
        if alt is None or alt.questao_id != q.id:
            continue
        respondidas += 1
        acertos += bool(alt.correta)
        if not atrasado:
            db.session.add(TorneioResposta(torneio_id=t.id, participante_id=p.id, questao_id=q.id, alternativa_id=alt.id, acertou=bool(alt.correta)))
    p.respondidas = 0 if atrasado else respondidas
    p.acertos = 0 if atrasado else acertos
    p.pontuacao = p.acertos * PONTOS_POR_ACERTO
    db.session.flush()
    db.session.refresh(p)
    return p


# ---------- encerramento ----------
def encerrar(t: Torneio) -> bool:
    """Fecha, fixa as posições e paga os prêmios. Idempotente: só quem vence a disputa pelo status executa."""
    if t.status != "aberto":
        return False
    if db.session.execute(update(Torneio).where(Torneio.id == t.id, Torneio.status == "aberto").values(status="finalizado", finalizado_em=clock.agora())).rowcount != 1:
        return False
    db.session.refresh(t)
    for p in participantes(t):  # quem começou e não enviou fecha com 0 ponto
        if p.iniciou_em and not p.finalizado:
            p.finalizado, p.terminou_em, p.pontuacao = True, prazo(t, p), 0
    db.session.flush()
    rank = ranking(t)
    for pos, p in enumerate(rank, 1):
        p.posicao = pos
        if pos <= 3 and (p.pontuacao or 0) > 0 and not p.recompensa_paga:
            xp_v, mo_v = getattr(t, f"recompensa_xp_{pos}") or 0, getattr(t, f"recompensa_moedas_{pos}") or 0
            u = db.session.get(Usuario, p.usuario_id)
            chave = f"torneio:{t.id}:{u.id}"
            if xp_v:
                xp.conceder_xp(u, xp_v, "torneio", chave, referencia=t.id)
            if mo_v:
                wallet.creditar(u.id, mo_v, "torneio", chave, descricao=f"{pos}º lugar em {t.nome}", ref_tipo="torneio", ref_id=t.id)
            p.recompensa_paga = True
        if p.usuario_id:
            notificacoes.criar(p.usuario_id, "competicao", f"Você ficou em {pos}º lugar" if pos <= 3 else "Competição encerrada",
                               f"{t.nome}: {p.acertos} acertos.", f"/competicoes/{t.id}")
    return True


def encerrar_vencidos() -> int:
    """Fecha o que passou do fim + tolerância (quem ainda joga tem prazo <= fim). Chamado ao abrir páginas e pelo CLI."""
    corte = clock.agora() - TOLERANCIA
    n = 0
    for t in db.session.scalars(select(Torneio).where(Torneio.status == "aberto", Torneio.fim <= corte)):
        n += encerrar(t)
    return n
