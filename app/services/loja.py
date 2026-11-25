"""Compra, equipar e uso de itens. Compra = débito no ledger + entrega do item na MESMA transação:
se qualquer passo falhar, nada é cobrado. O chamador faz o commit."""
from datetime import timedelta

from sqlalchemy import select, update

from app import clock
from app.extensions import db
from app.models import InventarioItem, ItemLoja, Usuario
from app.services import inventory, streak, wallet

SLOT = {"borda": "borda_ativa", "badge": "badge_ativa", "efeito": "efeito_ativo", "fundo": "fundo_ativo"}
ROTULO_SLOT = {"borda": "borda", "badge": "badge", "efeito": "efeito de fundo", "fundo": "fundo de perfil"}


class ErroLoja(Exception):
    """Mensagem em português, segura para mostrar ao usuário."""


def _item_comprável(item: ItemLoja | None) -> ItemLoja:
    if item is None or not item.ativo or (item.disponivel_ate and item.disponivel_ate < clock.agora()):
        raise ErroLoja("Este item não está mais disponível.")
    return item


def comprar(usuario: Usuario, item_id: int, token: str) -> ItemLoja:
    item = _item_comprável(db.session.get(ItemLoja, item_id))
    inv = db.session.scalar(select(InventarioItem).where(InventarioItem.usuario_id == usuario.id, InventarioItem.item_id == item.id))
    if inv and not item.eh_consumivel and not inv.expirado:
        raise ErroLoja("Você já tem este item.")
    # consumível: cada compra tem a sua chave (o token vem do formulário, repetir o POST não cobra duas vezes)
    chave = f"loja:{usuario.id}:{item.id}:{token[:40]}" if item.eh_consumivel or inv else f"loja:{usuario.id}:{item.id}"
    try:
        lanc = wallet.debitar(usuario.id, item.preco, "compra_loja", chave, descricao=f"Compra: {item.nome}",
                              ref_tipo="item", ref_id=item.id)
    except wallet.SaldoInsuficiente:
        raise ErroLoja("Moedas insuficientes.")
    if lanc.novo:  # repetição do mesmo POST: não entrega de novo
        inventory.conceder(usuario.id, item, "compra")
    db.session.refresh(usuario, ["moedas"])
    return item


def _meu_item(usuario: Usuario, item_id: int) -> InventarioItem:
    inv = db.session.scalar(select(InventarioItem).where(InventarioItem.usuario_id == usuario.id, InventarioItem.item_id == item_id))
    if inv is None:
        raise ErroLoja("Item não encontrado no seu inventário.")
    return inv


def equipar(usuario: Usuario, item_id: int) -> str:
    inv = _meu_item(usuario, item_id)
    item = inv.item
    if item.tipo not in SLOT or not item.css_class:
        raise ErroLoja("Este item não pode ser equipado.")
    if inv.expirado:
        raise ErroLoja("Este item expirou.")
    for outro in db.session.scalars(select(InventarioItem).join(ItemLoja).where(
            InventarioItem.usuario_id == usuario.id, ItemLoja.tipo == item.tipo, InventarioItem.equipado.is_(True))):
        outro.equipado = False
    inv.equipado = True
    setattr(usuario, SLOT[item.tipo], item.css_class)
    return item.nome


def desequipar(usuario: Usuario, tipo: str) -> None:
    if tipo not in SLOT:
        raise ErroLoja("Tipo inválido.")
    for inv in db.session.scalars(select(InventarioItem).join(ItemLoja).where(
            InventarioItem.usuario_id == usuario.id, ItemLoja.tipo == tipo, InventarioItem.equipado.is_(True))):
        inv.equipado = False
    setattr(usuario, SLOT[tipo], None)


def sanear_expirados(usuario: Usuario) -> None:
    """Tira do perfil cosméticos temporários vencidos."""
    for inv in db.session.scalars(select(InventarioItem).where(InventarioItem.usuario_id == usuario.id, InventarioItem.equipado.is_(True),
                                                              InventarioItem.expira_em.is_not(None), InventarioItem.expira_em < clock.agora())):
        desequipar(usuario, inv.item.tipo)


def usar(usuario: Usuario, item_id: int) -> str:
    """Consome 1 carga de boost ou escudo. O UPDATE condicional impede gastar a mesma carga duas vezes."""
    inv = _meu_item(usuario, item_id)
    item = inv.item
    if not item.eh_consumivel:
        raise ErroLoja("Este item é equipado, não consumido.")
    agora = clock.agora()
    if item.tipo in ("boost_xp", "boost_moeda"):
        pct, exp = ("boost_xp_pct", "boost_xp_expira") if item.tipo == "boost_xp" else ("boost_coin_pct", "boost_coin_expira")
        if getattr(usuario, exp) and getattr(usuario, exp) > agora:
            raise ErroLoja("Já existe um boost deste tipo ativo. Espere terminar para usar outro.")
    r = db.session.execute(update(InventarioItem).where(InventarioItem.id == inv.id, InventarioItem.quantidade > 0)
                           .values(quantidade=InventarioItem.quantidade - 1), execution_options={"synchronize_session": "fetch"})
    if not r.rowcount:
        raise ErroLoja("Você não tem mais cargas deste item.")
    if item.tipo in ("boost_xp", "boost_moeda"):
        setattr(usuario, pct, item.valor_boost)
        setattr(usuario, exp, agora + timedelta(hours=item.duracao_h))
        return f"{item.nome} ativado por {item.duracao_h}h."
    streak.adicionar_escudos(usuario, item.valor_boost or 1)
    return f"+{item.valor_boost or 1} escudo(s) de sequência."
