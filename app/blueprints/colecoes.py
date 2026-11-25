"""Coleções e favoritos de questões."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db, limiter
from app.models import ColecaoItem, Questao
from app.services import colecoes as svc

bp = Blueprint("colecoes", __name__, url_prefix="/colecoes")
POR_PAGINA = 20


@bp.route("/")
@login_required
def index():
    lista = svc.listar(current_user.id)
    db.session.commit()  # "Favoritos" pode ter sido criada agora
    return render_template("colecoes/index.html", lista=lista)


@bp.post("/nova")
@login_required
@limiter.limit("30 per hour")
def nova():
    try:
        c = svc.criar(current_user, request.form.get("nome", ""))
        db.session.commit()
        flash("Coleção criada.", "sucesso")
        return redirect(url_for("colecoes.ver", cid=c.id))
    except svc.ErroColecao as e:
        db.session.rollback()
        flash(str(e), "erro")
        return redirect(url_for("colecoes.index"))


@bp.route("/<int:cid>")
@login_required
def ver(cid):
    c = svc.da_pessoa(current_user.id, cid) or abort(404)
    pag = db.paginate(select(ColecaoItem).where(ColecaoItem.colecao_id == c.id).order_by(ColecaoItem.id.desc()),
                      page=request.args.get("page", 1, type=int), per_page=POR_PAGINA, error_out=False)
    return render_template("colecoes/ver.html", c=c, pag=pag)


@bp.post("/<int:cid>/excluir")
@login_required
def excluir(cid):
    c = svc.da_pessoa(current_user.id, cid) or abort(404)
    if c.eh_favoritos:
        flash("A coleção Favoritos não pode ser excluída.", "erro")
        return redirect(url_for("colecoes.ver", cid=c.id))
    db.session.delete(c)
    db.session.commit()
    flash("Coleção excluída. As questões continuam no banco.", "sucesso")
    return redirect(url_for("colecoes.index"))


@bp.post("/api/questao/<int:qid>")
@login_required
@limiter.limit("120 per minute")
def api_definir(qid):
    """Usada pelo menu "Salvar" da questão. Corpo: {colecao_id: int, presente: bool}."""
    d = request.get_json(silent=True) or {}
    if not isinstance(d.get("colecao_id"), int) or not isinstance(d.get("presente"), bool):
        return jsonify(erro="Pedido inválido."), 400
    try:
        svc.definir(current_user.id, d["colecao_id"], qid, d["presente"])
        db.session.commit()
    except svc.ErroColecao as e:
        db.session.rollback()
        return jsonify(erro=str(e)), 400
    return jsonify(ok=True, presente=d["presente"])
