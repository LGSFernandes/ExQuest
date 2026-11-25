import time

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, limiter, oauth
from app.forms import FormLogin, FormRecuperarSenha, FormRedefinirSenha, FormRegistro
from app.models import Usuario
from app.security import ip_usuario, limpar_texto, url_interna_segura
from app.services import audit
from app.services import auth as svc

bp = Blueprint("auth", __name__)
MSG_GENERICA = "E-mail ou senha incorretos."


def _entrar(u: Usuario, lembrar: bool = False) -> None:
    session.clear()  # evita fixação de sessão
    login_user(u, remember=lembrar)
    session["sv"] = u.session_version or 0
    session["login_ts"] = int(time.time())  # contas sem senha (Google) provam "presença" por login recente em ações destrutivas
    session.permanent = True
    audit.registrar("login", u.id, request=request)
    db.session.commit()


def init_google(app) -> None:
    if app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]:
        oauth.register("google", client_id=app.config["GOOGLE_CLIENT_ID"], client_secret=app.config["GOOGLE_CLIENT_SECRET"],
                       server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                       client_kwargs={"scope": "openid email profile",
                                      "timeout": (app.config["HTTP_CONNECT_TIMEOUT"], app.config["HTTP_READ_TIMEOUT"])})


def _google_ativo() -> bool:
    return bool(current_app.config["GOOGLE_CLIENT_ID"] and current_app.config["GOOGLE_CLIENT_SECRET"])


@bp.app_context_processor
def _ctx():
    return {"google_ativo": _google_ativo}


@bp.route("/entrar", methods=["GET", "POST"])
@limiter.limit("20 per minute; 100 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.inicio"))
    form = FormLogin()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if svc.bloqueado(email):
            flash("Muitas tentativas. Aguarde 15 minutos ou redefina sua senha.", "erro")
            return render_template("auth/login.html", form=form), 429
        u = svc.verificar_credenciais(email, form.senha.data)
        if u is None:
            svc.registrar_falha(email, ip_usuario())
            db.session.commit()
            flash(MSG_GENERICA, "erro")
            return render_template("auth/login.html", form=form), 401
        if u.is_banido:
            flash("Esta conta está suspensa. Fale com o suporte.", "erro")
            return render_template("auth/login.html", form=form), 403
        _entrar(u, form.lembrar.data)
        return redirect(url_interna_segura(request.args.get("next"), url_for("main.inicio")))
    return render_template("auth/login.html", form=form)


@bp.route("/sair", methods=["POST"])
@login_required
def logout():
    audit.registrar("logout", current_user.id, request=request)
    db.session.commit()
    logout_user()
    session.clear()
    flash("Você saiu da sua conta.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/cadastro", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("main.inicio"))
    form = FormRegistro()
    if form.validate_on_submit():
        u = svc.criar_conta(nome=form.nome.data, sobrenome=form.sobrenome.data, username=form.username.data,
                            email=form.email.data, senha=form.senha.data)
        audit.registrar("registro", u.id, request=request)
        db.session.commit()
        _entrar(u)
        flash("Conta criada. Bem-vindo ao ExQuest!", "sucesso")
        return redirect(url_for("main.inicio"))
    return render_template("auth/registro.html", form=form)


@bp.route("/recuperar-senha", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def recuperar():
    form = FormRecuperarSenha()
    if form.validate_on_submit():
        u = Usuario.query.filter_by(email=form.email.data.strip().lower()).first()
        if u and not u.is_banido:
            token = svc.criar_token_recuperacao(u)
            db.session.commit()
            svc.enviar_email_recuperacao(u, current_app.config["BASE_URL"] + url_for("auth.redefinir", token=token))  # origem confiável: nunca o Host da requisição
            db.session.commit()  # grava o job de e-mail (modo queue)
        # resposta idêntica exista a conta ou não
        return render_template("auth/recuperar_enviado.html")
    return render_template("auth/recuperar.html", form=form)


@bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def redefinir(token):
    t = svc.token_valido(token)
    if t is None:
        flash("Este link expirou ou já foi usado. Peça um novo.", "erro")
        return redirect(url_for("auth.recuperar"))
    form = FormRedefinirSenha()
    if form.validate_on_submit():
        if not svc.redefinir_senha(t, form.nova_senha.data):
            db.session.rollback()
            flash("Este link expirou ou já foi usado. Peça um novo.", "erro")
            return redirect(url_for("auth.recuperar"))
        audit.registrar("senha_redefinida", t.usuario_id, request=request)
        db.session.commit()
        flash("Senha alterada. Entre com a nova senha.", "sucesso")
        return redirect(url_for("auth.login"))
    return render_template("auth/redefinir.html", form=form)


@bp.route("/entrar/google")
def google():
    if not _google_ativo():
        abort(404)
    return oauth.google.authorize_redirect(url_for("auth.google_retorno", _external=True))


@bp.route("/entrar/google/retorno")
def google_retorno():
    if not _google_ativo():
        abort(404)
    try:
        token = oauth.google.authorize_access_token()
        info = token.get("userinfo") or oauth.google.userinfo()
    except Exception:  # noqa: BLE001 - state inválido, usuário cancelou etc.
        current_app.logger.warning("falha no retorno do Google", exc_info=True)
        flash("Não foi possível entrar com o Google. Tente novamente.", "erro")
        return redirect(url_for("auth.login"))
    email, sub = (info.get("email") or "").lower(), info.get("sub")
    if not email or not sub or not info.get("email_verified"):
        flash("O Google não confirmou o seu e-mail, então não podemos usá-lo para entrar.", "erro")
        return redirect(url_for("auth.login"))
    u = Usuario.query.filter_by(google_id=sub).first() or Usuario.query.filter_by(email=email).first()
    if u is None:
        u = svc.criar_conta(nome=limpar_texto(info.get("given_name") or email.split("@")[0], 80) or "Aluno",
                            sobrenome=limpar_texto(info.get("family_name") or "-", 80) or "-",
                            username=svc.username_livre(email.split("@")[0]), email=email, google_id=sub)
    elif u.google_id and u.google_id != sub:
        flash("Este e-mail já está vinculado a outra conta do Google.", "erro")
        return redirect(url_for("auth.login"))
    elif not u.google_id:
        u.google_id = sub  # vincula: e-mail verificado pelo Google
        if u.senha_hash:  # o cadastro local não verifica o e-mail: quem pré-registrou o e-mail de outra pessoa perde a senha e as sessões
            u.senha_hash, u.session_version = None, (u.session_version or 0) + 1
            flash("Vinculamos sua conta ao Google. Se você tinha senha, use Esqueci a senha para criar uma nova.", "aviso")
    if u.is_banido:
        flash("Esta conta está suspensa. Fale com o suporte.", "erro")
        return redirect(url_for("auth.login"))
    _entrar(u, True)
    return redirect(url_for("main.inicio"))
