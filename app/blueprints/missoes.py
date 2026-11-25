from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.services import missoes as svc

bp = Blueprint("missoes", __name__, url_prefix="/missoes")


@bp.route("/")
@login_required
def index():
    itens = svc.listar(current_user)
    return render_template("missoes/index.html", diarias=[i for i in itens if i["missao"].periodo == "dia"],
                           semanais=[i for i in itens if i["missao"].periodo == "semana"])


@bp.post("/<slug>/resgatar")
@login_required
def resgatar(slug):
    try:
        m = svc.resgatar(current_user, slug)
        db.session.commit()
        flash(f"Recompensa resgatada: +{m.xp} XP e +{m.moedas} moedas.", "sucesso")
    except svc.ErroMissao as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(url_for("missoes.index"))
