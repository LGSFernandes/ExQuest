"""XP e níveis. Cada ganho tem uma chave única (idempotente) e fica registrado em xp_eventos.
Ao cruzar um nível com recompensa, ela é concedida uma única vez (moedas pelo ledger + item opcional)."""
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import RecompensaNivelConcedida, Usuario, XpEvento
from app.services import inventory, niveis, wallet


@dataclass
class ResultadoXp:
    concedido: int = 0
    repetido: bool = False
    nivel_antes: int = 1
    nivel_depois: int = 1
    recompensas: list = field(default_factory=list)  # [{"nivel", "moedas", "item"}]

    @property
    def subiu(self) -> bool:
        return self.nivel_depois > self.nivel_antes


def conceder_xp(usuario: Usuario, valor: int, origem: str, chave: str, referencia=None) -> ResultadoXp:
    nivel_antes = niveis.nivel_por_xp(usuario.xp or 0)
    res = ResultadoXp(nivel_antes=nivel_antes, nivel_depois=nivel_antes)
    if valor <= 0:
        return res
    try:
        with db.session.begin_nested():
            db.session.add(XpEvento(usuario_id=usuario.id, valor=valor, origem=origem, chave=chave,
                                    referencia=None if referencia is None else str(referencia)))
            db.session.flush()
            db.session.execute(update(Usuario).where(Usuario.id == usuario.id).values(xp=func.coalesce(Usuario.xp, 0) + valor),
                               execution_options={"synchronize_session": "fetch"})
    except IntegrityError:
        res.repetido = True
        return res
    db.session.refresh(usuario, ["xp"])
    res.concedido = valor
    res.nivel_depois = niveis.nivel_por_xp(usuario.xp)
    catalogo = niveis.recompensa_nivel_catalogo()
    for n in range(nivel_antes + 1, res.nivel_depois + 1):
        if n in catalogo and _marcar_recompensa(usuario.id, n):
            r = catalogo[n]
            if r["moedas"]:
                wallet.creditar(usuario.id, r["moedas"], "recompensa", f"nivel:{usuario.id}:{n}",
                                descricao=f"Recompensa do nível {n}", ref_tipo="nivel", ref_id=n)
            if r["item"]:
                inventory.conceder_por_slug(usuario.id, r["item"], origem="recompensa")
            res.recompensas.append({"nivel": n, **r})
    return res


def conceder_recompensas_pendentes(usuario: Usuario) -> list:
    """Contas antigas podem ter nível sem a recompensa registrada; concede o que faltar (uma única vez por nível)."""
    nivel, feitas = niveis.nivel_por_xp(usuario.xp or 0), []
    for n, r in niveis.recompensa_nivel_catalogo().items():
        if n <= nivel and _marcar_recompensa(usuario.id, n):
            if r["moedas"]:
                wallet.creditar(usuario.id, r["moedas"], "recompensa", f"nivel:{usuario.id}:{n}",
                                descricao=f"Recompensa do nível {n}", ref_tipo="nivel", ref_id=n)
            if r["item"]:
                inventory.conceder_por_slug(usuario.id, r["item"], origem="recompensa")
            feitas.append({"nivel": n, **r})
    return feitas


def _marcar_recompensa(usuario_id: int, nivel: int) -> bool:
    """True só na primeira vez (a unicidade do banco decide, mesmo com requisições simultâneas)."""
    ja = db.session.scalar(select(RecompensaNivelConcedida.id).where(
        RecompensaNivelConcedida.usuario_id == usuario_id, RecompensaNivelConcedida.nivel == nivel))
    if ja:
        return False
    try:
        with db.session.begin_nested():
            db.session.add(RecompensaNivelConcedida(usuario_id=usuario_id, nivel=nivel))
            db.session.flush()
        return True
    except IntegrityError:
        return False
