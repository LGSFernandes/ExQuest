"""Inventário: concessão de itens (loja, recompensas, admin). Equipar/usar entram na fase de loja."""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import clock
from app.extensions import db
from app.models import InventarioItem, ItemLoja

log = logging.getLogger(__name__)


def conceder(usuario_id: int, item: ItemLoja, origem: str = "compra", quantidade: int = 1) -> InventarioItem:
    """Cosméticos: no máximo 1 por usuário (repetir é no-op, ou renova a validade se temporário).
    Consumíveis (boost/escudo): acumulam quantidade."""
    inv = db.session.scalar(select(InventarioItem).where(InventarioItem.usuario_id == usuario_id, InventarioItem.item_id == item.id))
    validade = clock.agora() + timedelta(days=item.duracao_dias) if item.duracao_dias else None
    if inv is not None:
        if item.eh_consumivel:
            inv.quantidade = (inv.quantidade or 0) + quantidade
        elif validade is not None:
            inv.expira_em = max(inv.expira_em or validade, validade)
        return inv
    try:
        with db.session.begin_nested():
            inv = InventarioItem(usuario_id=usuario_id, item_id=item.id, quantidade=quantidade if item.eh_consumivel else 1,
                                 equipado=False, origem=origem, expira_em=validade)
            db.session.add(inv)
            db.session.flush()
    except IntegrityError:  # corrida: outro processo inseriu primeiro
        inv = db.session.scalar(select(InventarioItem).where(InventarioItem.usuario_id == usuario_id, InventarioItem.item_id == item.id))
        if item.eh_consumivel:
            inv.quantidade = (inv.quantidade or 0) + quantidade
    return inv


def conceder_por_slug(usuario_id: int, slug: str, origem: str = "recompensa"):
    item = db.session.scalar(select(ItemLoja).where(ItemLoja.slug == slug))
    if item is None:
        log.warning("item de recompensa inexistente no catálogo: %s", slug)
        return None
    return conceder(usuario_id, item, origem)
