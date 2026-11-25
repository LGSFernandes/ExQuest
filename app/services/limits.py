"""Limites diários de questões e simulados. O consumo é um UPDATE condicional: vale mesmo com requisições simultâneas."""
from sqlalchemy import or_, update

from app import clock
from app.extensions import db
from app.models import Usuario

_SYNC = {"synchronize_session": "fetch"}


def resetar_se_novo_dia(usuario_id: int) -> None:
    hoje = clock.hoje()
    db.session.execute(
        update(Usuario).where(Usuario.id == usuario_id, or_(Usuario.ultimo_reset.is_(None), Usuario.ultimo_reset < hoje))
        .values(questoes_hoje=0, simulados_hoje=0, ultimo_reset=hoje), execution_options=_SYNC)


def _consumir(usuario, coluna: str, limite, bonus: bool) -> bool:
    resetar_se_novo_dia(usuario.id)
    col = getattr(Usuario, coluna)
    if limite is None:  # ilimitado: só contabiliza
        db.session.execute(update(Usuario).where(Usuario.id == usuario.id).values({coluna: col + 1}), execution_options=_SYNC)
        return True
    r = db.session.execute(update(Usuario).where(Usuario.id == usuario.id, col < limite).values({coluna: col + 1}), execution_options=_SYNC)
    if r.rowcount:
        return True
    if bonus:  # questões bônus (ganhas em missões) valem depois do limite do dia
        r = db.session.execute(update(Usuario).where(Usuario.id == usuario.id, Usuario.questoes_bonus > 0)
                               .values(questoes_bonus=Usuario.questoes_bonus - 1), execution_options=_SYNC)
        return bool(r.rowcount)
    return False


def consumir_questao(usuario) -> bool:
    return _consumir(usuario, "questoes_hoje", usuario.limite("questoes_dia"), bonus=True)


def consumir_simulado(usuario) -> bool:
    return _consumir(usuario, "simulados_hoje", usuario.limite("simulados_dia"), bonus=False)


def restante_questoes(usuario) -> int | None:
    """None = ilimitado. Inclui bônus. Não altera nada."""
    lim = usuario.limite("questoes_dia")
    if lim is None:
        return None
    usadas = usuario.questoes_hoje if usuario.ultimo_reset == clock.hoje() else 0
    return max(0, lim - (usadas or 0)) + (usuario.questoes_bonus or 0)


def restante_simulados(usuario) -> int | None:
    lim = usuario.limite("simulados_dia")
    if lim is None:
        return None
    usados = usuario.simulados_hoje if usuario.ultimo_reset == clock.hoje() else 0
    return max(0, lim - (usados or 0))
