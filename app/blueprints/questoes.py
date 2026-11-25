"""Banco de questões: filtro, resposta (múltipla escolha e discursiva) e correção no servidor."""
import secrets
import time

from flask import Blueprint, abort, jsonify, render_template, request, session
from flask_login import current_user, login_required
from sqlalchemy import func, select

from app.extensions import db, limiter
from app.models import Alternativa, ColecaoItem, Materia, Questao, QuestaoRespondidaSessao
from app.security import limpar_texto
from app.services import colecoes, competicoes, destaques, grading, limits, niveis

bp = Blueprint("questoes", __name__, url_prefix="/questoes")

DIFICULDADES = (("facil", "Fácil"), ("medio", "Média"), ("dificil", "Difícil"))


def filtrar(materia_ids, dificuldades, conteudo, tipo, usuario_id=None):
    q = select(Questao).join(Materia).where(Questao.ativo.is_(True), Materia.ativo.is_(True))
    if usuario_id:
        q = q.where(Questao.id.notin_(competicoes.ids_bloqueados(usuario_id)))
    if materia_ids:
        q = q.where(Questao.materia_id.in_(materia_ids))
    if dificuldades:
        q = q.where(Questao.dificuldade.in_([d for d in dificuldades if d in dict(DIFICULDADES)]))
    if conteudo:
        q = q.where(Questao.conteudo.ilike(f"%{conteudo.replace('%', '').replace('_', '')}%"))
    if tipo in ("multipla", "discursiva"):
        q = q.where(Questao.tipo == tipo)
    return q


def _resumo_limite():
    r = limits.restante_questoes(current_user)
    return {"restante": r, "limite": current_user.limite_questoes_dia}


@bp.get("/sugestoes")
@login_required
@limiter.limit("60 per minute")
def sugestoes():
    """Autocomplete do campo Assunto: até 8 assuntos distintos de questões disponíveis. Só dados públicos do banco de questões."""
    q = request.args.get("q", "").strip()[:50].replace("%", "").replace("_", "")
    if len(q) < 2:
        return jsonify(itens=[])
    itens = db.session.scalars(select(Questao.conteudo).join(Materia).where(
        Questao.ativo.is_(True), Materia.ativo.is_(True), Questao.conteudo.ilike(f"%{q}%")).distinct().order_by(Questao.conteudo).limit(8)).all()
    resp = jsonify(itens=[i for i in itens if i])
    resp.headers["Cache-Control"] = "private, max-age=60"
    return resp


@bp.route("/")
@login_required
def index():
    materias = destaques.materias_ativas()
    ids = request.args.getlist("materia_id", type=int)
    difs = request.args.getlist("dificuldade")
    conteudo = request.args.get("conteudo", "").strip()[:100]
    tipo = request.args.get("tipo", "")
    sessao = request.args.get("sessao_id", "")[:64] or secrets.token_hex(8)
    questao, disponiveis, colecao = None, 0, None
    cid = request.args.get("colecao_id", type=int)
    if cid:
        colecao = colecoes.da_pessoa(current_user.id, cid) or abort(404)
    if ids or colecao:
        base = (select(Questao).where(Questao.ativo.is_(True), Questao.id.in_(select(ColecaoItem.questao_id).where(
            ColecaoItem.colecao_id == colecao.id))) if colecao else filtrar(ids, difs, conteudo, tipo, current_user.id))
        feitas = select(QuestaoRespondidaSessao.questao_id).where(
            QuestaoRespondidaSessao.usuario_id == current_user.id, QuestaoRespondidaSessao.sessao_id == sessao)
        base = base.where(Questao.id.not_in(feitas), Questao.id.notin_(competicoes.ids_bloqueados(current_user.id)))
        disponiveis = db.session.scalar(select(func.count()).select_from(base.subquery()))
        questao = db.session.scalar(base.order_by(func.random()).limit(1))
        if questao:  # o tempo de resposta é contado a partir daqui, no servidor
            session["q_visto"] = {"id": questao.id, "t": time.time()}
    salvar = None
    if questao:
        salvar = {"lista": [c for c, _ in colecoes.listar(current_user.id)], "marcadas": colecoes.ids_da_questao(current_user.id, questao.id)}
        db.session.commit()  # "Favoritos" pode ter sido criada agora
    return render_template("questoes/index.html", materias=materias, colecao=colecao, salvar=salvar, questao=questao, materia_ids=ids, dificuldades=difs,
                           conteudo=conteudo, tipo=tipo, sessao_id=sessao, disponiveis=disponiveis,
                           dificuldades_lista=DIFICULDADES, lim=_resumo_limite())


def _tempo_ms(questao_id: int):
    v = session.get("q_visto")
    if v and v.get("id") == questao_id:
        return max(0, int((time.time() - v["t"]) * 1000))
    return None


def _estado(res: grading.Resultado):
    return {"xp_ganho": res.xp, "moedas_ganhas": res.moedas, "primeira_vez": res.primeira_vez,
            "xp_total": current_user.xp or 0, "moedas_total": current_user.moedas or 0, "nivel": current_user.nivel,
            "progresso_nivel": current_user.progresso_nivel,
            "subiu_nivel": res.subiu_nivel, "recompensas_nivel": res.recompensas_nivel,
            "streak": current_user.streak.sequencia_atual if current_user.streak else 0, "limite": _resumo_limite()}


def _lembrar_sessao(questao_id: int, sessao_id: str):
    if sessao_id:
        db.session.add(QuestaoRespondidaSessao(usuario_id=current_user.id, questao_id=questao_id, sessao_id=sessao_id[:64]))


@bp.post("/responder")
@login_required
@limiter.limit("120 per minute")
def responder():
    d = request.get_json(silent=True) or {}
    questao = db.session.get(Questao, d.get("questao_id")) if isinstance(d.get("questao_id"), int) else None
    alt = db.session.get(Alternativa, d.get("alternativa_id")) if isinstance(d.get("alternativa_id"), int) else None
    if not questao or not questao.ativo or questao.tipo == "discursiva" or not alt or alt.questao_id != questao.id:
        return jsonify(erro="Resposta inválida."), 400
    if questao.id in competicoes.ids_bloqueados(current_user.id):
        return jsonify(erro="Esta questão faz parte de uma competição em andamento. Ela volta a ficar disponível quando a competição terminar."), 403
    if not limits.consumir_questao(current_user):
        db.session.rollback()
        return jsonify(erro="Você usou todas as questões de hoje.", limite=True), 429
    res = grading.registrar(current_user, questao, acertou=bool(alt.correta), modo="questao", alternativa_id=alt.id,
                            tempo_ms=_tempo_ms(questao.id), ip_request=request)
    _lembrar_sessao(questao.id, d.get("sessao_id") or "")
    db.session.commit()
    certa = questao.alternativa_correta
    return jsonify(acertou=bool(alt.correta), alternativa_correta_id=certa.id if certa else None,
                   explicacao=questao.explicacao or "", **_estado(res))


@bp.post("/responder-discursiva")
@login_required
@limiter.limit("30 per minute")
def responder_discursiva():
    d = request.get_json(silent=True) or {}
    texto = limpar_texto(d.get("resposta_texto") or "", 2000, multilinha=True)
    questao = db.session.get(Questao, d.get("questao_id")) if isinstance(d.get("questao_id"), int) else None
    if not questao or not questao.ativo or questao.tipo != "discursiva" or len(texto.split()) < 2:
        return jsonify(erro="Escreva uma resposta para enviar."), 400
    if not limits.consumir_questao(current_user):
        db.session.rollback()
        return jsonify(erro="Você usou todas as questões de hoje.", limite=True), 429
    ok, nota, fb = grading.avaliar_discursiva(questao.enunciado, questao.resposta_correta, texto)
    res = grading.registrar(current_user, questao, acertou=ok, modo="questao", texto=texto, nota=nota, feedback=fb,
                            tempo_ms=_tempo_ms(questao.id), ip_request=request)
    _lembrar_sessao(questao.id, d.get("sessao_id") or "")
    db.session.commit()
    return jsonify(acertou=ok, nota=round(nota * 100), feedback=fb, gabarito=questao.resposta_correta or "",
                   explicacao=questao.explicacao or "", **_estado(res))
