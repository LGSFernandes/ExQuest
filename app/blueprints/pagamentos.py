from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app import clock
from app.extensions import db, limiter
from app.models import Assinatura, Pagamento
from app.providers.base import ProviderIndisponivel
from app.services import pagamentos as svc
from app.services import plans, premium

bp = Blueprint("pagamentos", __name__)


@bp.route("/loja/moedas")
@login_required
def moedas():
    return render_template("pagamentos/moedas.html", pacotes=svc.PACOTES, provs=svc.provedores_disponiveis(), nomes=svc.NOME_PROVEDOR,
                           primeira=svc._primeira_compra(current_user.id), brl=plans.formatar_brl)


@bp.route("/premium")
@login_required
def premium_pagina():
    premium.expirar_vencidos()
    db.session.commit()
    historico = db.session.scalars(select(Pagamento).where(Pagamento.usuario_id == current_user.id).order_by(Pagamento.criado_em.desc()).limit(20)).all()
    return render_template("pagamentos/premium.html", planos=plans.PLANOS, ciclos=plans.CICLOS, beneficios=plans.beneficios, brl=plans.formatar_brl,
                           provs=svc.provedores_disponiveis(), nomes=svc.NOME_PROVEDOR, historico=historico, ordem=plans.ORDEM)


@bp.post("/pagamentos/checkout")
@login_required
@limiter.limit("10 per minute")
def checkout():
    tipo, produto, prov = request.form.get("tipo", ""), request.form.get("produto", ""), request.form.get("provider", "")
    try:
        pg = svc.criar_pedido(current_user, tipo, produto, prov)
    except (ValueError, ProviderIndisponivel) as e:
        db.session.rollback()
        flash(str(e), "erro")
        return redirect(url_for("pagamentos.premium_pagina" if tipo == "premium" else "pagamentos.moedas"))
    return redirect(pg._url)  # externo: o provedor hospeda o pagamento (nenhum dado de cartão passa por aqui)


@bp.route("/pagamentos/retorno/<int:pid>")
@login_required
@limiter.limit("30 per minute")
def retorno(pid):
    pg = db.session.get(Pagamento, pid)
    if not pg or pg.usuario_id != current_user.id:
        abort(404)
    agora = clock.agora()
    if pg.status in ("criado", "pendente") and (agora - (pg.atualizado_em or pg.criado_em)).total_seconds() >= 6:
        try:  # no máximo uma consulta ao provedor a cada 6 s por pagamento, mesmo com F5 ou várias abas
            pg.atualizado_em = agora
            db.session.commit()
            svc.reconciliar(pg)
            db.session.commit()
        except ProviderIndisponivel:
            db.session.rollback()
    db.session.refresh(pg)
    return render_template("pagamentos/retorno.html", pg=pg)


@bp.route("/premium/assinaturas")
@login_required
def assinaturas():
    itens = db.session.scalars(select(Assinatura).where(Assinatura.usuario_id == current_user.id).order_by(Assinatura.inicio.desc())).all()
    return render_template("pagamentos/assinaturas.html", itens=itens, nomes=plans.PLANOS)
