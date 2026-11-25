from datetime import timedelta

from sqlalchemy import case, func, select

from app import clock
from app.extensions import db
from app.models import Materia, Questao, RespostaUsuario


def por_materia(uid: int):
    """[(Materia, total, acertos)] das matérias em que o usuário respondeu algo."""
    return db.session.execute(
        select(Materia, func.count(RespostaUsuario.id), func.coalesce(func.sum(case((RespostaUsuario.acertou.is_(True), 1), else_=0)), 0))
        .join(Questao, Questao.materia_id == Materia.id).join(RespostaUsuario, RespostaUsuario.questao_id == Questao.id)
        .where(RespostaUsuario.usuario_id == uid).group_by(Materia.id).order_by(func.count(RespostaUsuario.id).desc())).all()


def ultimos_dias(uid: int, n: int = 7):
    """[(data, total, acertos)] dos últimos n dias (dia local), do mais antigo ao mais novo, incluindo dias vazios."""
    hoje = clock.hoje()
    dias = [hoje - timedelta(days=i) for i in range(n - 1, -1, -1)]
    linhas = db.session.execute(select(RespostaUsuario.data_resposta, RespostaUsuario.acertou).where(
        RespostaUsuario.usuario_id == uid, RespostaUsuario.data_resposta >= clock.inicio_do_dia_utc(dias[0]))).all()
    tot, ace = {d: 0 for d in dias}, {d: 0 for d in dias}
    for quando, ok in linhas:
        d = clock.para_local(quando).date()
        if d in tot:
            tot[d] += 1
            ace[d] += bool(ok)
    return [(d, tot[d], ace[d]) for d in dias]


def resumo(uid: int):
    total, acertos = db.session.execute(select(func.count(RespostaUsuario.id), func.coalesce(func.sum(case((RespostaUsuario.acertou.is_(True), 1), else_=0)), 0))
                                        .where(RespostaUsuario.usuario_id == uid)).one()
    return total, int(acertos), round(acertos * 100 / total) if total else 0
