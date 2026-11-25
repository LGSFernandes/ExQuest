"""Fila de tarefas em banco: tira trabalho lento (e-mail, etc.) da requisição, com retentativa e recuperação de falhas.

- `enfileirar(tipo, payload)`: em JOBS_MODE=eager executa na hora (mesmo código, sem worker); em `queue` grava em `jobs`.
- `executar_pendentes()`: reivindica cada job com UPDATE condicional (vários workers não pegam o mesmo job),
  executa, e em falha reagenda com espera exponencial (30 s, 2 min, 8 min...) até `max_tentativas` (depois "morto").
- Job preso em "executando" por mais de 10 min (worker caiu) volta para "pendente".
- Sem dependências novas e funciona em SQLite e PostgreSQL. A fila é por banco; o payload não deve conter segredos duradouros.
"""
import json
import logging
from datetime import timedelta

from flask import current_app
from sqlalchemy import select, update

from app import clock
from app.extensions import db
from app.models.jobs import Job

log = logging.getLogger(__name__)
HANDLERS: dict = {}
PRESO_APOS = timedelta(minutes=10)


def handler(tipo: str):
    def reg(fn):
        HANDLERS[tipo] = fn
        return fn
    return reg


@handler("email")
def _email(p: dict) -> None:
    from app.services import emails
    emails.enviar_agora(p["to"], p["subject"], p["body"])


def enfileirar(tipo: str, payload: dict, *, max_tentativas: int = 5) -> Job | None:
    """Em modo eager executa já (falha é registrada, não propaga). Em queue grava e devolve o Job (o commit é de quem chamou)."""
    if tipo not in HANDLERS:
        raise ValueError(f"tipo de job desconhecido: {tipo}")
    if current_app.config["JOBS_MODE"] != "queue":
        try:
            HANDLERS[tipo](payload)
        except Exception:  # noqa: BLE001 - o chamador não pode falhar por causa de um e-mail
            log.exception("job %s falhou (modo eager)", tipo)
        return None
    j = Job(tipo=tipo, payload_json=json.dumps(payload), max_tentativas=max_tentativas)
    db.session.add(j)
    return j


def _liberar_presos() -> int:
    r = db.session.execute(update(Job).where(Job.status == "executando", Job.iniciado_em < clock.agora() - PRESO_APOS)
                           .values(status="pendente", iniciado_em=None))
    db.session.commit()
    return r.rowcount or 0


def _reivindicar(job_id: int) -> bool:
    r = db.session.execute(update(Job).where(Job.id == job_id, Job.status == "pendente")
                           .values(status="executando", iniciado_em=clock.agora(), tentativas=Job.tentativas + 1))
    db.session.commit()
    return r.rowcount == 1


def executar_pendentes(limite: int = 20) -> dict:
    _liberar_presos()
    ids = db.session.scalars(select(Job.id).where(Job.status == "pendente", Job.proxima_em <= clock.agora())
                             .order_by(Job.proxima_em, Job.id).limit(limite)).all()
    res = {"ok": 0, "falha": 0, "morto": 0}
    for jid in ids:
        if not _reivindicar(jid):
            continue  # outro worker pegou
        j = db.session.get(Job, jid)
        try:
            HANDLERS[j.tipo](j.payload)
            j.status, j.concluido_em, j.erro = "ok", clock.agora(), None
            j.payload_json = "{}"  # o payload pode conter link de redefinição: não fica guardado depois de usado
            res["ok"] += 1
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            j = db.session.get(Job, jid)
            j.erro = f"{type(e).__name__}: {e}"[:300]
            if j.tentativas >= j.max_tentativas:
                j.status, j.payload_json = "morto", "{}"
                res["morto"] += 1
                log.error("job %s #%s esgotou as tentativas: %s", j.tipo, j.id, j.erro)
            else:
                j.status = "pendente"
                j.proxima_em = clock.agora() + timedelta(seconds=30 * 4 ** (j.tentativas - 1))
                res["falha"] += 1
        db.session.commit()
    return res


def limpar_antigos(dias: int = 14) -> int:
    """Remove jobs concluídos há mais de `dias` (os 'mortos' ficam para diagnóstico)."""
    r = db.session.execute(Job.__table__.delete().where(Job.status == "ok", Job.concluido_em < clock.agora() - timedelta(days=dias)))
    db.session.commit()
    return r.rowcount or 0
