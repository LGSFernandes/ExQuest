"""Simulados. A sessão vive no servidor: as questões sorteadas, o relógio e a nota não dependem do navegador."""
import json
import secrets
from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select, update

from app import clock
from app.blueprints.questoes import DIFICULDADES, filtrar
from app.extensions import db
from app.models import Alternativa, Materia, Questao, RespostaUsuario, SimuladoSessao
from app.security import limpar_texto
from app.services import competicoes, grading, limits, xp

bp = Blueprint("simulados", __name__, url_prefix="/simulados")
TOLERANCIA = timedelta(seconds=45)  # atraso de rede aceito além do tempo


def _minha(token: str) -> SimuladoSessao:
    s = db.session.scalar(select(SimuladoSessao).where(SimuladoSessao.token == token,
                                                      SimuladoSessao.usuario_id == current_user.id))
    if not s:
        abort(404)
    return s


@bp.route("/")
@login_required
def escolher():
    materias = db.session.execute(
        select(Materia, func.count(Questao.id)).join(Questao, Questao.materia_id == Materia.id)
        .where(Materia.ativo.is_(True), Questao.ativo.is_(True)).group_by(Materia.id).order_by(Materia.nome)).all()
    recentes = db.session.scalars(select(SimuladoSessao).where(SimuladoSessao.usuario_id == current_user.id)
                                  .order_by(SimuladoSessao.iniciado_em.desc()).limit(5)).all()
    return render_template("simulados/escolher.html", materias=materias, recentes=recentes,
                           dificuldades_lista=DIFICULDADES, restante=limits.restante_simulados(current_user),
                           maximo=current_user.max_questoes_simulado)


@bp.post("/iniciar")
@login_required
def iniciar():
    f = request.form
    ids, difs = f.getlist("materia_id", type=int), f.getlist("dificuldade")
    conteudo, tipo = f.get("conteudo", "").strip()[:100], f.get("tipo", "")
    qtd = max(1, min(f.get("quantidade", 10, type=int), current_user.max_questoes_simulado))
    sorteadas = db.session.scalars(filtrar(ids, difs, conteudo, tipo, current_user.id).order_by(func.random()).limit(qtd)).all()
    if not sorteadas:
        flash("Nenhuma questão encontrada com esses filtros.", "aviso")
        return redirect(url_for("simulados.escolher"))
    if not limits.consumir_simulado(current_user):
        db.session.rollback()
        flash("Você já fez todos os simulados de hoje. O limite renova à meia-noite ou com um plano Premium.", "aviso")
        return redirect(url_for("simulados.escolher"))
    s = SimuladoSessao(usuario_id=current_user.id, token=secrets.token_urlsafe(24), limite_segundos=len(sorteadas) * 120,
                       questoes_json=json.dumps([q.id for q in sorteadas]), total=len(sorteadas),
                       filtros_json=json.dumps({"materias": ids, "dificuldades": difs, "conteudo": conteudo, "tipo": tipo}))
    db.session.add(s)
    db.session.commit()
    return redirect(url_for("simulados.fazer", token=s.token))


def _questoes(s: SimuladoSessao) -> list[Questao]:
    ids = json.loads(s.questoes_json)
    por_id = {q.id: q for q in db.session.scalars(select(Questao).where(Questao.id.in_(ids)))}
    return [por_id[i] for i in ids if i in por_id]


@bp.route("/<token>")
@login_required
def fazer(token):
    s = _minha(token)
    questoes = _questoes(s)
    if s.status != "em_andamento":
        resp = {r.questao_id: r for r in db.session.scalars(select(RespostaUsuario).where(RespostaUsuario.simulado_id == s.id,
                                                                                         RespostaUsuario.usuario_id == current_user.id))}
        return render_template("simulados/resultado.html", s=s, questoes=questoes, resp=resp, bloqueadas=set(competicoes.ids_bloqueados(current_user.id)))
    fim = s.iniciado_em + timedelta(seconds=s.limite_segundos)
    if clock.agora() > fim + TOLERANCIA:  # abandonado: fecha sem pontuar
        s.status, s.finalizado_em = "expirado", clock.agora()
        db.session.commit()
        flash("O tempo desse simulado acabou antes do envio.", "aviso")
        return redirect(url_for("simulados.escolher"))
    restante = max(0, int((fim - clock.agora()).total_seconds()))
    return render_template("simulados/fazer.html", s=s, questoes=questoes, restante=restante)


@bp.post("/<token>/finalizar")
@login_required
def finalizar(token):
    s = _minha(token)
    if s.status != "em_andamento":
        return redirect(url_for("simulados.fazer", token=token))
    if db.session.execute(update(SimuladoSessao).where(SimuladoSessao.id == s.id, SimuladoSessao.status == "em_andamento")
                          .values(status="finalizado")).rowcount != 1:  # duplo envio: só um corrige e paga
        return redirect(url_for("simulados.fazer", token=token))
    db.session.refresh(s)
    agora = clock.agora()
    atrasado = agora > s.iniciado_em + timedelta(seconds=s.limite_segundos) + TOLERANCIA
    acertos = xp_total = moedas_total = 0
    travadas = set(competicoes.ids_bloqueados(current_user.id))  # inscrito em competição aberta: essas questões não são corrigidas aqui
    for q in _questoes(s):
        if q.id in travadas:
            continue
        campo = request.form.get(f"q{q.id}", "")
        if q.tipo == "discursiva":
            texto = limpar_texto(campo, 2000, multilinha=True)
            if not texto:
                continue
            ok, nota, fb = grading.avaliar_discursiva(q.enunciado, q.resposta_correta, texto)
            kw = dict(texto=texto, nota=nota, feedback=fb)
        else:
            alt = db.session.get(Alternativa, int(campo)) if campo.isdigit() else None
            if not alt or alt.questao_id != q.id:
                continue
            ok, kw = bool(alt.correta), dict(alternativa_id=alt.id)
        r = grading.registrar(current_user, q, acertou=ok, modo="simulado", simulado_id=s.id, recompensar=not atrasado,
                              ip_request=request, **kw)
        acertos += ok
        xp_total += r.xp
        moedas_total += r.moedas
    s.status = "expirado" if atrasado else "finalizado"
    s.finalizado_em, s.acertos, s.xp_total, s.moedas_total = agora, acertos, xp_total, moedas_total
    db.session.commit()
    if atrasado:
        flash("Enviado depois do tempo: as respostas foram corrigidas, mas sem XP e moedas.", "aviso")
    return redirect(url_for("simulados.fazer", token=token))
