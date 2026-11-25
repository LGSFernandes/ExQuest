"""Ranking global e por matéria, com recorte de período (semana, mês, sempre)."""
from datetime import timedelta

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import distinct, func, select

from app import clock
from app.extensions import db
from app.models import Materia, Questao, RespostaUsuario, Usuario, XpEvento
from app.services import destaques

bp = Blueprint("ranking", __name__, url_prefix="/ranking")
POR_PAGINA = 15
PERIODOS = (("semana", "Esta semana"), ("mes", "Este mês"), ("sempre", "Sempre"))


def _desde(periodo: str):
    if periodo == "semana":
        return clock.inicio_do_dia_utc(clock.inicio_da_semana())
    if periodo == "mes":
        return clock.inicio_do_dia_utc(clock.hoje().replace(day=1))
    return None


@bp.route("/")
@login_required
def index():
    materia_id = request.args.get("materia_id", type=int)
    periodo = request.args.get("periodo", "sempre")
    if periodo not in dict(PERIODOS):
        periodo = "sempre"
    pagina = max(1, min(request.args.get("page", 1, type=int), 1000))
    materia = db.session.get(Materia, materia_id) if materia_id else None
    if materia_id and not materia:
        abort(404)
    desde = _desde(periodo)

    # pontos: XP acumulado (global) ou questões distintas acertadas (por matéria)
    if materia:
        pts = func.count(distinct(RespostaUsuario.questao_id)).label("pts")
        q = (select(RespostaUsuario.usuario_id.label("uid"), pts).join(Questao, Questao.id == RespostaUsuario.questao_id)
             .where(Questao.materia_id == materia.id, RespostaUsuario.acertou.is_(True)).group_by(RespostaUsuario.usuario_id))
        if desde:
            q = q.where(RespostaUsuario.data_resposta >= desde)
    elif desde:
        pts = func.sum(XpEvento.valor).label("pts")
        q = select(XpEvento.usuario_id.label("uid"), pts).where(XpEvento.criado_em >= desde, XpEvento.valor > 0).group_by(XpEvento.usuario_id)
    else:
        pts = Usuario.xp.label("pts")
        q = select(Usuario.id.label("uid"), pts).where(Usuario.xp > 0)
    sub = q.subquery()
    recorte = f"{materia.id if materia else 0}:{periodo}"  # chave do cache: o recorte, não o usuário

    def _pagina():
        total = db.session.scalar(select(func.count()).select_from(sub)) or 0
        linhas = db.session.execute(
            select(Usuario.id, sub.c.pts).join(sub, Usuario.id == sub.c.uid).where(Usuario.is_banido.is_(False))
            .order_by(sub.c.pts.desc(), Usuario.id).limit(POR_PAGINA).offset((pagina - 1) * POR_PAGINA)).all()
        return {"linhas": [[u, int(p)] for u, p in linhas], "total": total}

    def _minha():
        meus = db.session.scalar(select(sub.c.pts).where(sub.c.uid == current_user.id))
        pos = (db.session.scalar(select(func.count()).select_from(sub).where(sub.c.pts > meus)) + 1) if meus else None
        return {"meus": int(meus) if meus is not None else None, "pos": pos}

    dados = destaques.ranking_pagina(f"{recorte}:p{pagina}", _pagina)
    eu = destaques.ranking_pagina(f"{recorte}:u{current_user.id}", _minha)
    return render_template("ranking/index.html", linhas=destaques.usuarios_na_ordem(dados["linhas"]), offset=(pagina - 1) * POR_PAGINA, pagina=pagina,
                           paginas=max(1, -(-dados["total"] // POR_PAGINA)), materia=materia, periodo=periodo, periodos=PERIODOS,
                           materias=destaques.materias_ativas(), minha_pos=eu["pos"], meus=eu["meus"], unidade="questões" if materia else "XP")
