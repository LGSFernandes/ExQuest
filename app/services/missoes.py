"""Missões diárias e semanais. O progresso é calculado a partir das respostas reais (nada é contado por gancho,
então não há como divergir); só o resgate é gravado. Questões repetidas no período contam uma vez."""
from dataclasses import dataclass

from sqlalchemy import func, select, update

from app import clock
from app.extensions import db
from app.models import MissaoProgresso, RespostaUsuario, SimuladoSessao
from app.services import notificacoes, wallet, xp


@dataclass(frozen=True)
class Missao:
    slug: str
    titulo: str
    descricao: str
    periodo: str  # dia | semana
    meta: int
    xp: int
    moedas: int
    medida: str   # respondidas | acertos | dias | simulados


CATALOGO = (
    Missao("dia-responder-5", "Aquecimento", "Responda {meta} questões diferentes hoje.", "dia", 5, 20, 10, "respondidas"),
    Missao("dia-acertar-3", "Pontaria", "Acerte {meta} questões diferentes hoje.", "dia", 3, 25, 15, "acertos"),
    Missao("dia-simulado", "Prova do dia", "Conclua um simulado hoje.", "dia", 1, 40, 20, "simulados"),
    Missao("semana-responder-30", "Ritmo da semana", "Responda {meta} questões diferentes nesta semana.", "semana", 30, 100, 50, "respondidas"),
    Missao("semana-acertar-20", "Mira afiada", "Acerte {meta} questões diferentes nesta semana.", "semana", 20, 120, 60, "acertos"),
    Missao("semana-dias-5", "Constância", "Estude em {meta} dias diferentes nesta semana.", "semana", 5, 150, 80, "dias"),
)
POR_SLUG = {m.slug: m for m in CATALOGO}


def meta_para(usuario, m: Missao) -> int:
    """Meta efetiva: no plano gratuito (poucas questões por dia) a meta nunca passa do que o limite diário permite alcançar."""
    lim = usuario.limite("questoes_dia")
    if lim is None or m.medida not in ("respondidas", "acertos"):
        return m.meta
    teto = lim * (1 if m.periodo == "dia" else 7)
    return min(m.meta, max(1, int(teto * (0.7 if m.medida == "acertos" else 1))))


def periodo(m: Missao):
    """(chave, início em UTC naive)."""
    hoje = clock.hoje()
    if m.periodo == "dia":
        return hoje.isoformat(), clock.inicio_do_dia_utc(hoje)
    return clock.chave_semana(hoje), clock.inicio_do_dia_utc(clock.inicio_da_semana(hoje))


def progresso(uid: int, m: Missao, desde) -> int:
    R = RespostaUsuario
    base = [R.usuario_id == uid, R.data_resposta >= desde]
    if m.medida == "respondidas":
        return db.session.scalar(select(func.count(func.distinct(R.questao_id))).where(*base)) or 0
    if m.medida == "acertos":
        return db.session.scalar(select(func.count(func.distinct(R.questao_id))).where(*base, R.acertou.is_(True))) or 0
    if m.medida == "simulados":
        # simulado em branco não conta: precisa ter respondido ao menos metade das questões (no mínimo 1)
        feitos = 0
        for sid, total in db.session.execute(select(SimuladoSessao.id, SimuladoSessao.total).where(
                SimuladoSessao.usuario_id == uid, SimuladoSessao.status == "finalizado", SimuladoSessao.finalizado_em >= desde)):
            n = db.session.scalar(select(func.count()).select_from(R).where(R.simulado_id == sid)) or 0
            feitos += n >= max(1, (total or 0) // 2)
        return feitos
    # dias: dias locais distintos com resposta
    datas = db.session.scalars(select(R.data_resposta).where(*base)).all()
    return len({clock.para_local(d).date() for d in datas})


def listar(usuario) -> list[dict]:
    uid, out = usuario.id, []
    for m in CATALOGO:
        chave, desde = periodo(m)
        reg = db.session.scalar(select(MissaoProgresso).where(MissaoProgresso.usuario_id == uid, MissaoProgresso.missao_slug == m.slug,
                                                             MissaoProgresso.periodo_chave == chave))
        meta = meta_para(usuario, m)
        atual = min(progresso(uid, m, desde), meta)
        out.append({"missao": m, "meta": meta, "descricao": m.descricao.format(meta=meta), "atual": atual,
                    "pronta": atual >= meta and not (reg and reg.resgatada_em), "resgatada": bool(reg and reg.resgatada_em)})
    return out


class ErroMissao(Exception):
    pass


def resgatar(usuario, slug: str) -> Missao:
    m = POR_SLUG.get(slug)
    if m is None:
        raise ErroMissao("Missão inexistente.")
    chave, desde = periodo(m)
    meta = meta_para(usuario, m)
    if progresso(usuario.id, m, desde) < meta:
        raise ErroMissao("Esta missão ainda não foi concluída.")
    reg = db.session.scalar(select(MissaoProgresso).where(MissaoProgresso.usuario_id == usuario.id, MissaoProgresso.missao_slug == slug,
                                                         MissaoProgresso.periodo_chave == chave))
    if reg is None:
        try:
            with db.session.begin_nested():
                reg = MissaoProgresso(usuario_id=usuario.id, missao_slug=slug, periodo_chave=chave, progresso=meta, meta=meta,
                                      concluida_em=clock.agora())
                db.session.add(reg)
        except Exception:  # corrida com outro clique: a linha única já existe
            reg = db.session.scalar(select(MissaoProgresso).where(MissaoProgresso.usuario_id == usuario.id,
                                                                 MissaoProgresso.missao_slug == slug, MissaoProgresso.periodo_chave == chave))
    # só quem passa de resgatada_em NULL para preenchido paga
    if db.session.execute(update(MissaoProgresso).where(MissaoProgresso.id == reg.id, MissaoProgresso.resgatada_em.is_(None))
                          .values(resgatada_em=clock.agora())).rowcount != 1:
        raise ErroMissao("Você já resgatou esta missão.")
    chave_idem = f"missao:{usuario.id}:{slug}:{chave}"
    xp.conceder_xp(usuario, m.xp, "missao", chave_idem, referencia=reg.id)
    wallet.creditar(usuario.id, m.moedas, "missao", chave_idem, descricao=m.titulo, ref_tipo="missao", ref_id=reg.id)
    notificacoes.criar(usuario.id, "missao", f"Missão concluída: {m.titulo}", f"+{m.xp} XP e +{m.moedas} moedas.", "/missoes/")
    return m
