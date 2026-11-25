"""Competições para os alunos. Relógio, nota e ranking são do servidor."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app import clock
from app.extensions import db
from app.models import Torneio
from app.services import competicoes as svc

bp = Blueprint("competicoes", __name__, url_prefix="/competicoes")


def _torneio(tid: int) -> Torneio:
    t = db.session.get(Torneio, tid)
    if not t:
        abort(404)
    return t


@bp.route("/")
@login_required
def index():
    if svc.encerrar_vencidos():
        db.session.commit()
    todos = list(db.session.scalars(select(Torneio).where(Torneio.status != "cancelado").order_by(Torneio.inicio.desc()).limit(60)))
    ativos = [t for t in todos if t.fase in ("agendado", "em_andamento")]
    ativos.sort(key=lambda t: t.inicio)
    passados = [t for t in todos if t.fase not in ("agendado", "em_andamento")]
    minhas = {t.id: svc.meu(t, current_user.id) for t in todos}
    return render_template("competicoes/index.html", ativos=ativos, passados=passados, minhas=minhas,
                           usadas=svc.mes_usado(current_user.id), teto=current_user.limite("torneios_mes"))


@bp.route("/<int:tid>")
@login_required
def ver(tid):
    t = _torneio(tid)
    if svc.encerrar_vencidos():
        db.session.commit()
        db.session.refresh(t)
    p = svc.meu(t, current_user.id)
    return render_template("competicoes/ver.html", t=t, p=p, ranking=svc.ranking(t), motivo=svc.pode_entrar(current_user, t),
                           inscritos=len(svc.participantes(t)), tempo=svc.tempo_gasto)


@bp.post("/<int:tid>/entrar")
@login_required
def entrar(tid):
    t = _torneio(tid)
    try:
        svc.entrar(current_user, t)
        db.session.commit()
        flash("Inscrição confirmada.", "sucesso")
    except svc.ErroCompeticao as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(url_for("competicoes.ver", tid=tid))


@bp.post("/<int:tid>/comecar")
@login_required
def comecar(tid):
    t = _torneio(tid)
    try:
        svc.comecar(current_user, t)
        db.session.commit()
    except svc.ErroCompeticao as e:
        db.session.rollback()
        flash(str(e), "erro")
        return redirect(url_for("competicoes.ver", tid=tid))
    return redirect(url_for("competicoes.jogar", tid=tid))


@bp.route("/<int:tid>/jogar")
@login_required
def jogar(tid):
    t = _torneio(tid)
    p = svc.meu(t, current_user.id)
    if p is None or not p.iniciou_em or p.finalizado or t.status != "aberto":
        return redirect(url_for("competicoes.ver", tid=tid))
    restante = int((svc.prazo(t, p) - clock.agora()).total_seconds())
    # restante <= 0: o cronômetro envia na hora e o servidor fecha a participação
    return render_template("competicoes/jogar.html", t=t, questoes=svc.questoes(t), restante=max(0, restante))


@bp.post("/<int:tid>/enviar")
@login_required
def enviar(tid):
    t = _torneio(tid)
    respostas = {}
    for q in svc.questoes(t):
        v = request.form.get(f"q{q.id}", "")
        if v.isdigit():
            respostas[q.id] = int(v)
    try:
        p = svc.enviar(current_user, t, respostas)
        db.session.commit()
        flash("Prova enviada. A classificação final sai quando a competição encerrar.", "sucesso")
    except svc.ErroCompeticao as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(url_for("competicoes.ver", tid=tid))
