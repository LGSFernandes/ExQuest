"""Cabeçalhos de segurança, tratamento de erros e verificações globais de requisição."""
import logging
import uuid

from flask import abort, current_app, g, jsonify, render_template, request, session
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)

# CSP estrita: sem script/estilo inline (ADR-007). Valores dinâmicos de estilo são aplicados via CSSOM em app.js.
def montar_csp(cdn: str = "") -> str:
    """Com CDN_URL configurada, só essa origem (além de 'self') pode servir scripts, estilos, fontes e imagens."""
    extra = f" {cdn}" if cdn else ""
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self'{extra}",
        f"style-src 'self'{extra}",
        f"img-src 'self'{extra} data: blob:",
        f"font-src 'self'{extra}",
        "connect-src 'self'",
        "media-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
    ])


CSP = montar_csp()

MENSAGENS = {
    400: ("Requisição inválida", "Não foi possível entender o pedido. Recarregue a página e tente novamente."),
    403: ("Acesso negado", "Você não tem permissão para acessar este conteúdo."),
    404: ("Página não encontrada", "O endereço não existe ou o conteúdo foi removido."),
    405: ("Método não permitido", "Essa ação não é aceita neste endereço."),
    413: ("Arquivo grande demais", "O envio excede o tamanho permitido."),
    429: ("Muitas tentativas", "Aguarde um instante antes de tentar novamente."),
    500: ("Algo deu errado", "Ocorreu um erro inesperado. Já registramos o problema; tente novamente em instantes."),
}


def _quer_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json" \
        or request.headers.get("X-Requested-With") == "fetch"


def _erro(codigo: int, detalhe: str | None = None):
    titulo, msg = MENSAGENS.get(codigo, ("Erro", "Não foi possível concluir o pedido."))
    if _quer_json():
        return jsonify(ok=False, erro=detalhe or msg, codigo=codigo), codigo
    try:
        return render_template("errors/erro.html", codigo=codigo, titulo=titulo, mensagem=detalhe or msg), codigo
    except Exception:  # um handler de erro nunca pode lançar outro erro
        log.exception("falha ao renderizar página de erro %s", codigo)
        return f"{codigo} - {titulo}", codigo


_ULTIMA_MANUTENCAO = [float("-inf")]


def register_hooks(app) -> None:
    from app import clock

    @app.before_request
    def _manutencao_leve():
        """Fecha competições e expira Premium vencidos no máximo 1x por minuto por processo, sem depender de cron.
        É idempotente (várias réplicas não pagam em dobro). O agendador (`flask manutencao`) continua recomendado
        para quando não há visitas."""
        import time
        if app.config.get("TESTING") or not app.config.get("MANUTENCAO_INLINE", True) or request.endpoint in (None, "static") or time.monotonic() - _ULTIMA_MANUTENCAO[0] < 60:
            return None
        _ULTIMA_MANUTENCAO[0] = time.monotonic()
        from app.extensions import db
        from app.services import competicoes, premium
        try:
            competicoes.encerrar_vencidos()
            premium.expirar_vencidos()
            db.session.commit()
        except Exception:  # manutenção nunca derruba a requisição do aluno
            db.session.rollback()
            log.exception("falha na manutenção periódica")
        return None

    @app.template_filter("classe_css")
    def _classe_css(v):
        """Só deixa passar nomes de classe do catálogo (letras minúsculas, dígitos, hífen)."""
        import re
        return v if isinstance(v, str) and re.fullmatch(r"[a-z0-9-]{1,60}", v) else ""

    @app.template_filter("cor_css")
    def _cor_css(v):
        import re
        return v if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v) else ""

    @app.template_filter("resumo")
    def _resumo(texto, limite=90):
        """Prévia em texto simples de um enunciado: tira a marcação LaTeX e corta em fim de palavra (nunca no meio de uma fórmula)."""
        import re
        t = re.sub(r"\\[a-zA-Z]+|[$\\{}]", " ", texto or "")
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) <= limite:
            return t
        return t[:limite].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"

    @app.template_filter("datahora")
    def _datahora(dt):
        l = clock.para_local(dt)
        return l.strftime("%d/%m/%Y %H:%M") if l else ""

    @app.before_request
    def _antes():
        g.request_id = uuid.uuid4().hex[:12]
        # anexos de chat são privados: nunca servidos como arquivo estático público
        if request.path.startswith("/static/data/chat"):
            abort(404)
        if current_user.is_authenticated:
            # session_version: trocar a senha / "sair de todos os dispositivos" invalida sessões antigas
            sv = session.get("sv")
            if sv is None:
                session["sv"] = current_user.session_version or 0
            elif sv != (current_user.session_version or 0):
                logout_user()
                session.clear()

    @app.after_request
    def _depois(resp):
        h = resp.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["X-Request-ID"] = getattr(g, "request_id", "-")
        if "text/html" in (resp.content_type or ""):
            h["Content-Security-Policy"] = montar_csp(current_app.config.get("CDN_URL", ""))
            if current_user.is_authenticated or request.endpoint in ("auth.login", "auth.registro"):
                h["Cache-Control"] = "no-store"
        if current_app.config["IS_PRODUCTION"]:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp

    @app.context_processor
    def _contexto():
        from flask_wtf.csrf import generate_csrf
        from markupsafe import Markup, escape
        from app.navegacao import itens_visiveis
        return {
            "nav_itens": itens_visiveis,
            "tem_rota": lambda e: e in current_app.view_functions,
            "nao_lidas": lambda: __import__("app.services.notificacoes", fromlist=["x"]).nao_lidas(current_user.id) if current_user.is_authenticated else 0,
            "csrf_input": lambda: Markup(f'<input type="hidden" name="csrf_token" value="{escape(generate_csrf())}">'),
        }

    @app.errorhandler(CSRFError)
    def _csrf(e):
        return _erro(400, "Sua sessão expirou ou o formulário é inválido. Recarregue a página e tente novamente.")

    @app.errorhandler(HTTPException)
    def _http(e):
        return _erro(e.code or 500)

    @app.errorhandler(Exception)
    def _geral(e):
        log.exception("erro não tratado em %s %s", request.method, request.path)
        from app.extensions import db
        db.session.rollback()
        return _erro(500)
