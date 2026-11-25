"""Revisão espaçada (SM-2 simplificado). Erro entra na fila para amanhã (ver grading); cada acerto na revisão
espaça mais o próximo encontro; um novo erro volta o intervalo para 1 dia."""
from datetime import timedelta

from sqlalchemy import func, select

from app import clock
from app.extensions import db
from app.models import Questao, RevisaoQuestao


def devidas(uid: int):
    return select(RevisaoQuestao).join(Questao, Questao.id == RevisaoQuestao.questao_id).where(
        RevisaoQuestao.usuario_id == uid, RevisaoQuestao.ativo.is_(True), RevisaoQuestao.proxima_em <= clock.agora(),
        Questao.ativo.is_(True), Questao.tipo == "multipla")


def contar(uid: int) -> int:
    return db.session.scalar(select(func.count()).select_from(devidas(uid).subquery())) or 0


def proxima(uid: int) -> RevisaoQuestao | None:
    return db.session.scalar(devidas(uid).order_by(RevisaoQuestao.proxima_em).limit(1))


def acertou(uid: int, questao_id: int) -> None:
    r = db.session.scalar(select(RevisaoQuestao).where(RevisaoQuestao.usuario_id == uid, RevisaoQuestao.questao_id == questao_id))
    if r is None:
        return
    r.repeticoes += 1
    r.intervalo_dias = 1 if r.repeticoes == 1 else 3 if r.repeticoes == 2 else max(1, round((r.intervalo_dias or 3) * (r.facilidade or 2.5)))
    r.facilidade = min(3.0, (r.facilidade or 2.5) + 0.05)
    r.ultima_em, r.proxima_em = clock.agora(), clock.agora() + timedelta(days=r.intervalo_dias)
    if r.repeticoes >= 6:  # dominada: sai da fila
        r.ativo = False
