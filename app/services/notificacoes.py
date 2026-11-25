"""Notificações internas. `criar` não faz commit: entra na transação de quem chamou (some junto se ela falhar)."""
from sqlalchemy import func, select, update

from app.extensions import db
from app.models import Notificacao as Notif

LIMITE_POR_USUARIO = 200  # as mais antigas são apagadas ao passar disso


def criar(usuario_id: int, tipo: str, titulo: str, corpo: str | None = None, url: str | None = None, origem_id: int | None = None) -> None:
    if url and not (url.startswith("/") and not url.startswith("//") and "\\" not in url and url.isprintable()):
        url = None  # só links internos (a barra invertida vira "/" nos navegadores: "/\\evil.com" seria externo)
    db.session.add(Notif(usuario_id=usuario_id, tipo=tipo[:40], titulo=titulo[:120], corpo=(corpo or "")[:300] or None, url=url, origem_id=origem_id))


def nao_lidas(usuario_id: int) -> int:
    return db.session.scalar(select(func.count()).select_from(Notif).where(Notif.usuario_id == usuario_id, Notif.lida.is_(False))) or 0


def marcar_todas(usuario_id: int) -> None:
    db.session.execute(update(Notif).where(Notif.usuario_id == usuario_id, Notif.lida.is_(False)).values(lida=True))


def podar(usuario_id: int) -> None:
    ids = db.session.scalars(select(Notif.id).where(Notif.usuario_id == usuario_id).order_by(Notif.id.desc()).offset(LIMITE_POR_USUARIO)).all()
    if ids:
        db.session.execute(db.delete(Notif).where(Notif.id.in_(ids)))
