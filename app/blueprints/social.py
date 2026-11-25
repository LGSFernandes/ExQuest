"""Amigos e bloqueios (o chat fica em chat.py)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db, limiter
from app.models import Amizade, Usuario
from app.services import amizades as svc

bp = Blueprint("social", __name__)


def _voltar():
    return redirect(url_for("social.amigos"))


@bp.route("/amigos")
@login_required
def amigos():
    uid = current_user.id
    return render_template("social/amigos.html", amigos=svc.amigos(uid), recebidos=svc.recebidos(uid), enviados=svc.enviados(uid),
                           bloqueados=svc.bloqueados(uid), limite=current_user.limite("amigos"), total=svc.total_amigos(uid))


def _acao(fn, ok):
    try:
        fn()
        db.session.commit()
        flash(ok, "sucesso")
    except svc.ErroSocial as e:
        db.session.rollback()
        flash(str(e), "erro")
    return _voltar()


@bp.post("/amigos/pedir")
@login_required
@limiter.limit("20 per hour")
def pedir():
    alvo = svc.buscar(request.form.get("alvo", ""))
    try:
        resultado = svc.pedir(current_user, alvo)
        db.session.commit()
        flash("Vocês agora são amigos." if resultado == "aceito" else "Pedido enviado.", "sucesso")
    except svc.ErroSocial as e:
        db.session.rollback()
        flash(str(e), "erro")
    return _voltar()


def _rel(aid) -> Amizade:
    return db.session.get(Amizade, aid) or abort(404)


@bp.post("/amigos/<int:aid>/aceitar")
@login_required
def aceitar(aid):
    r = _rel(aid)
    return _acao(lambda: svc.aceitar(current_user, r), "Pedido aceito.")


@bp.post("/amigos/<int:aid>/recusar")
@login_required
def recusar(aid):
    r = _rel(aid)
    return _acao(lambda: svc.recusar(current_user, r), "Pedido recusado.")


@bp.post("/amigos/<int:aid>/desfazer")
@login_required
def desfazer(aid):
    r = _rel(aid)
    return _acao(lambda: svc.desfazer(current_user, r), "Feito.")


@bp.post("/amigos/remover/<int:uid>")
@login_required
def remover(uid):
    r = svc.relacao(current_user.id, uid) or abort(404)
    return _acao(lambda: svc.desfazer(current_user, r), "Amizade desfeita.")


@bp.post("/bloqueios/<int:uid>")
@login_required
def bloquear(uid):
    alvo = db.session.get(Usuario, uid) or abort(404)
    return _acao(lambda: svc.bloquear(current_user, alvo), "Usuário bloqueado.")


@bp.post("/bloqueios/<int:uid>/desfazer")
@login_required
def desbloquear(uid):
    return _acao(lambda: svc.desbloquear(current_user, uid), "Bloqueio removido.")
