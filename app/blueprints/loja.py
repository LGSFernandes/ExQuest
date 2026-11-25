import secrets

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app import clock
from app.extensions import db
from app.models import InventarioItem, ItemLoja
from app.services import loja as svc

bp = Blueprint("loja", __name__, url_prefix="/loja")
TIPOS = (("", "Tudo"), ("borda", "Bordas"), ("fundo", "Fundos de perfil"), ("efeito", "Efeitos de fundo"), ("badge", "Badges"),
         ("boost_xp", "Boost de XP"), ("boost_moeda", "Boost de moedas"), ("streak_shield", "Escudos"))
NOME_TIPO = {"borda": "Borda", "fundo": "Fundo de perfil", "efeito": "Efeito de fundo", "badge": "Badge", "boost_xp": "Boost de XP",
             "boost_moeda": "Boost de moedas", "streak_shield": "Escudo de sequência"}
ORDEM_RARIDADE = {"comum": 0, "raro": 1, "epico": 2, "lendario": 3}
NOME_RARIDADE = {"comum": "Comum", "raro": "Raro", "epico": "Épico", "lendario": "Lendário"}


def _voltar(padrao="loja.index"):
    return redirect(url_for(padrao))


@bp.route("/")
@login_required
def index():
    tipo = request.args.get("tipo", "")
    q = select(ItemLoja).where(ItemLoja.ativo.is_(True))
    q = q.where((ItemLoja.disponivel_ate.is_(None)) | (ItemLoja.disponivel_ate > clock.agora()))
    if tipo in dict(TIPOS) and tipo:
        q = q.where(ItemLoja.tipo == tipo)
    itens = sorted(db.session.scalars(q).all(), key=lambda i: (ORDEM_RARIDADE.get(i.raridade, 0), i.preco))
    meus = {i.item_id: i for i in db.session.scalars(select(InventarioItem).where(InventarioItem.usuario_id == current_user.id))}
    return render_template("loja/index.html", itens=itens, meus=meus, tipo=tipo, tipos=TIPOS, nome_tipo=NOME_TIPO,
                           nome_raridade=NOME_RARIDADE, token=secrets.token_hex(12))


@bp.post("/comprar/<int:item_id>")
@login_required
def comprar(item_id):
    try:
        item = svc.comprar(current_user, item_id, request.form.get("tk", "")[:40] or secrets.token_hex(8))
        db.session.commit()
        flash(f"{item.nome} comprado.", "sucesso")
    except svc.ErroLoja as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(request.referrer if request.referrer and request.referrer.startswith(request.host_url) else url_for("loja.index"))


@bp.route("/inventario")
@login_required
def inventario():
    svc.sanear_expirados(current_user)
    db.session.commit()
    itens = db.session.scalars(select(InventarioItem).join(ItemLoja).where(InventarioItem.usuario_id == current_user.id,
                                                                          (InventarioItem.quantidade > 0) | (ItemLoja.tipo.in_(svc.SLOT)))
                               .order_by(ItemLoja.tipo, ItemLoja.preco)).all()
    return render_template("loja/inventario.html", itens=itens, nome_tipo=NOME_TIPO, nome_raridade=NOME_RARIDADE)


@bp.post("/equipar/<int:item_id>")
@login_required
def equipar(item_id):
    try:
        nome = svc.equipar(current_user, item_id)
        db.session.commit()
        flash(f"{nome} equipado.", "sucesso")
    except svc.ErroLoja as e:
        db.session.rollback()
        flash(str(e), "erro")
    return _voltar("loja.inventario")


@bp.post("/desequipar/<tipo>")
@login_required
def desequipar(tipo):
    try:
        svc.desequipar(current_user, tipo)
        db.session.commit()
        flash(f"Você tirou o item de {svc.ROTULO_SLOT[tipo]}.", "sucesso")
    except svc.ErroLoja as e:
        db.session.rollback()
        flash(str(e), "erro")
    return _voltar("loja.inventario")


@bp.post("/usar/<int:item_id>")
@login_required
def usar(item_id):
    try:
        msg = svc.usar(current_user, item_id)
        db.session.commit()
        flash(msg, "sucesso")
    except svc.ErroLoja as e:
        db.session.rollback()
        flash(str(e), "erro")
    return _voltar("loja.inventario")
