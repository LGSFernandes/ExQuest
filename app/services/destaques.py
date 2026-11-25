"""Dados muito consultados e iguais para todos, servidos pelo cache (app/cache.py): matérias, ranking e destaques da home.

Só ids e números entram no cache (JSON); os objetos de usuário vêm do banco por id (uma consulta indexada), então
cosméticos, banimentos e avatares nunca ficam velhos. TTL curto = ranking atualiza em até TTL_RANKING segundos."""
from sqlalchemy import select

from app import cache
from app.extensions import db
from app.models import Materia, Usuario

TTL_MATERIAS = 300
TTL_RANKING = 30
TTL_TOP = 60


def materias_ativas() -> list[dict]:
    return cache.obter("materias", "ativas", TTL_MATERIAS, lambda: [
        {"id": m.id, "nome": m.nome} for m in db.session.scalars(select(Materia).where(Materia.ativo.is_(True)).order_by(Materia.nome))])


def materias_mudaram() -> None:
    cache.invalidar("materias")


def ranking_pagina(chave: str, calcular):
    """`calcular()` devolve {"linhas": [[uid, pts], ...], "total": n}; resultado em cache por TTL_RANKING."""
    return cache.obter("ranking", chave, TTL_RANKING, calcular)


def usuarios_na_ordem(pares) -> list[tuple[Usuario, int]]:
    """[[uid, pts], ...] -> [(Usuario, pts), ...] na mesma ordem; quem foi banido entre o cálculo e agora some."""
    ids = [int(u) for u, _ in pares]
    if not ids:
        return []
    por_id = {u.id: u for u in db.session.scalars(select(Usuario).where(Usuario.id.in_(ids), Usuario.is_banido.is_(False)))}
    return [(por_id[int(u)], p) for u, p in pares if int(u) in por_id]


def top_xp(n: int = 5) -> list[Usuario]:
    ids = cache.obter("top", f"xp{n}", TTL_TOP, lambda: list(db.session.scalars(
        select(Usuario.id).where(Usuario.is_banido.is_(False), Usuario.xp > 0).order_by(Usuario.xp.desc(), Usuario.id).limit(n))))
    return [u for u, _ in usuarios_na_ordem([[i, 0] for i in ids])]
