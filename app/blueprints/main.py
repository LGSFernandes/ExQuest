from flask import Blueprint, Response, current_app, render_template
from flask_login import current_user, login_required
from sqlalchemy import case, func, select

from app import clock
from app.extensions import db
from app.models import Materia, Questao, RespostaUsuario, RevisaoQuestao, Usuario
from app.services import destaques, limits, streak, xp

bp = Blueprint("main", __name__)


def _painel():
    u = current_user
    if xp.conceder_recompensas_pendentes(u):
        db.session.commit()
    dias, ativa_hoje, em_risco = streak.sequencia_exibida(u.streak)
    por_materia = db.session.execute(
        select(Materia, func.count(RespostaUsuario.id), func.coalesce(func.sum(case((RespostaUsuario.acertou.is_(True), 1), else_=0)), 0))
        .join(Questao, Questao.materia_id == Materia.id).join(RespostaUsuario, RespostaUsuario.questao_id == Questao.id)
        .where(RespostaUsuario.usuario_id == u.id).group_by(Materia.id).order_by(func.count(RespostaUsuario.id).desc())).all()
    ultimas = db.session.execute(
        select(RespostaUsuario, Questao).join(Questao, Questao.id == RespostaUsuario.questao_id)
        .where(RespostaUsuario.usuario_id == u.id).order_by(RespostaUsuario.data_resposta.desc()).limit(5)).all()
    devidas = db.session.scalar(select(func.count(RevisaoQuestao.id)).where(
        RevisaoQuestao.usuario_id == u.id, RevisaoQuestao.ativo.is_(True), RevisaoQuestao.proxima_em <= clock.agora()))
    top = destaques.top_xp(5)
    return dict(dias=dias, ativa_hoje=ativa_hoje, em_risco=em_risco, por_materia=por_materia, ultimas=ultimas,
                devidas=devidas or 0, top=top, restante_q=limits.restante_questoes(u), restante_s=limits.restante_simulados(u),
                escudos=(u.streak.escudos if u.streak else 0))


@bp.route("/")
def inicio():
    if current_user.is_authenticated:
        return render_template("dashboard.html", **_painel())
    return render_template("landing.html")


@bp.get("/healthz")
def saude():
    """Verificação de saúde para balanceador/orquestrador: confirma que o processo responde e o banco está acessível."""
    try:
        db.session.execute(select(1))
    except Exception:  # noqa: BLE001
        return Response("db indisponivel", 503, mimetype="text/plain", headers={"Cache-Control": "no-store"})
    return Response("ok", 200, mimetype="text/plain", headers={"Cache-Control": "no-store"})


@bp.route("/termos")
def termos():
    return render_template("legal/termos.html")


@bp.route("/privacidade")
def privacidade():
    return render_template("legal/privacidade.html")


_PUBLICAS = ("/", "/termos", "/privacidade", "/entrar", "/cadastro")


@bp.route("/robots.txt")
def robots():
    base = current_app.config["BASE_URL"].rstrip("/")
    txt = f"User-agent: *\nAllow: /\nDisallow: /webhooks/\nDisallow: /pagamentos/\nDisallow: /configuracoes\nSitemap: {base}/sitemap.xml\n"
    return Response(txt, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    base = current_app.config["BASE_URL"].rstrip("/")
    urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in _PUBLICAS)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                    mimetype="application/xml")
