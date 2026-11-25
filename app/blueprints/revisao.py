"""Caderno de erros: reencontra as questões que você errou, em intervalos crescentes."""
import time

from flask import Blueprint, jsonify, render_template, request, session
from flask_login import current_user, login_required
from sqlalchemy import select

from app.blueprints.questoes import _estado, _tempo_ms
from app.extensions import db, limiter
from app.models import Alternativa, Questao, RevisaoQuestao
from app.services import competicoes, grading, revisao

bp = Blueprint("revisao", __name__, url_prefix="/revisao")


@bp.route("/")
@login_required
def index():
    r = revisao.proxima(current_user.id)
    if r:
        session["q_visto"] = {"id": r.questao_id, "t": time.time()}
    return render_template("revisao/index.html", r=r, questao=r.questao if r else None, devidas=revisao.contar(current_user.id))


@bp.post("/responder")
@login_required
@limiter.limit("120 per minute")
def responder():
    d = request.get_json(silent=True) or {}
    questao = db.session.get(Questao, d.get("questao_id")) if isinstance(d.get("questao_id"), int) else None
    alt = db.session.get(Alternativa, d.get("alternativa_id")) if isinstance(d.get("alternativa_id"), int) else None
    if not questao or not questao.ativo or questao.tipo != "multipla" or not alt or alt.questao_id != questao.id:
        return jsonify(erro="Resposta inválida."), 400
    if questao.id in competicoes.ids_bloqueados(current_user.id):
        return jsonify(erro="Esta questão faz parte de uma competição em andamento."), 403
    if db.session.scalar(select(RevisaoQuestao.id).where(RevisaoQuestao.usuario_id == current_user.id, RevisaoQuestao.questao_id == questao.id)) is None:
        return jsonify(erro="Esta questão não está na sua revisão."), 403
    res = grading.registrar(current_user, questao, acertou=bool(alt.correta), modo="revisao", alternativa_id=alt.id,
                            tempo_ms=_tempo_ms(questao.id), ip_request=request)
    if alt.correta:
        revisao.acertou(current_user.id, questao.id)
    db.session.commit()
    certa = questao.alternativa_correta
    return jsonify(acertou=bool(alt.correta), alternativa_correta_id=certa.id if certa else None,
                   explicacao=questao.explicacao or "", **_estado(res))
