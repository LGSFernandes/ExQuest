from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.models import Notificacao
from app.services import notificacoes as svc

bp = Blueprint("notificacoes", __name__, url_prefix="/notificacoes")


@bp.route("/")
@login_required
def index():
    pag = db.paginate(select(Notificacao).where(Notificacao.usuario_id == current_user.id).order_by(Notificacao.id.desc()),
                      page=request.args.get("page", 1, type=int), per_page=20, error_out=False)
    return render_template("notificacoes/index.html", pag=pag)


@bp.post("/lidas")
@login_required
def marcar_lidas():
    svc.marcar_todas(current_user.id)
    svc.podar(current_user.id)
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":  # tela otimista (app.js): já se atualizou sozinha
        return "", 204
    return redirect(url_for("notificacoes.index"))


@bp.route("/<int:nid>/abrir")
@login_required
def abrir(nid):
    n = db.session.get(Notificacao, nid)
    if n is None or n.usuario_id != current_user.id:
        abort(404)
    n.lida = True
    db.session.commit()
    return redirect(n.url or url_for("notificacoes.index"))
