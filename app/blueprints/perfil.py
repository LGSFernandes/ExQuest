import time

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from app.extensions import bcrypt, db, limiter
from app.forms.perfil import FONTES, FormPerfil, FormSenha
from app.models import Denuncia, RespostaUsuario, Questao, Usuario
from app.security import limpar_texto, validar_senha
from app.services import amizades, audit, conta, estatisticas, streak, uploads

bp = Blueprint("perfil", __name__)


@bp.route("/perfil")
@login_required
def meu():
    return redirect(url_for("perfil.ver", username=current_user.username))


@bp.route("/perfil/<username>")
@login_required
def ver(username):
    u = db.session.scalar(select(Usuario).where(Usuario.username == username.lower(), Usuario.is_banido.is_(False)))
    if u is None:
        abort(404)
    meu_perfil = u.id == current_user.id
    stats = historico = None
    if meu_perfil or u.mostrar_stats:
        total, acertos, pct = estatisticas.resumo(u.id)
        stats = dict(total=total, acertos=acertos, pct=pct, materias=estatisticas.por_materia(u.id), dias=estatisticas.ultimos_dias(u.id))
    if meu_perfil or u.mostrar_historico:
        historico = db.session.execute(select(RespostaUsuario, Questao).join(Questao, Questao.id == RespostaUsuario.questao_id)
                                       .where(RespostaUsuario.usuario_id == u.id).order_by(RespostaUsuario.data_resposta.desc()).limit(8)).all()
    lista_amigos = amizades.amigos(u.id) if (meu_perfil or u.mostrar_amigos) else None
    dias, _, _ = streak.sequencia_exibida(u.streak)
    return render_template("perfil/ver.html", u=u, meu_perfil=meu_perfil, stats=stats, historico=historico, sequencia=dias, lista_amigos=lista_amigos,
                           motivos_denuncia=MOTIVOS_DENUNCIA)


def _salvar_imagem(campo, pasta, atual, permitir_gif, prefixo):
    """Troca a imagem só se a nova for válida; apaga a antiga depois de gravar a nova."""
    try:
        nome = uploads.salvar_imagem(campo.data, pasta, permitir_gif=permitir_gif, prefixo=prefixo)
    except uploads.UploadInvalido as e:
        flash(str(e), "erro")
        return atual
    uploads.remover_apos_commit(pasta, atual)
    return nome


@bp.route("/configuracoes", methods=["GET", "POST"])
@login_required
def configuracoes():
    u = current_user
    form = FormPerfil(prefix="p", obj=u if request.method == "GET" else None)
    senha = FormSenha(prefix="s")
    if request.method == "GET":
        cores = (u.nick_gradiente or "").split(",")
        form.nick_cor.data = cores[0] if u.nick_gradiente else (u.nick_cor or "")
        form.nick_cor2.data = cores[1] if len(cores) > 1 else ""
        form.nick_fonte.data = u.nick_fonte or ""
    if request.method == "POST" and request.form.get("acao") == "perfil" and form.validate_on_submit():
        u.nome, u.sobrenome, u.biografia = form.nome.data, form.sobrenome.data, form.biografia.data
        u.mostrar_stats, u.mostrar_historico, u.mostrar_amigos = form.mostrar_stats.data, form.mostrar_historico.data, form.mostrar_amigos.data
        u.bloquear_pedidos_amizade = form.bloquear_pedidos_amizade.data
        if form.icon_file.data and form.icon_file.data.filename:
            u.icon_path = _salvar_imagem(form.icon_file, "icon", u.icon_path, u.pode("upload_gif"), "ic_")
        elif form.remover_icon.data:
            uploads.remover_apos_commit("icon", u.icon_path); u.icon_path = None
        if form.banner_file.data and form.banner_file.data.filename:
            if u.pode_upload_banner:
                u.banner_path = _salvar_imagem(form.banner_file, "banner", u.banner_path, u.pode_upload_gif, "bn_")
            else:
                flash("Banner personalizado é um recurso do plano Intermediário ou superior.", "aviso")
        elif form.remover_banner.data:
            uploads.remover_apos_commit("banner", u.banner_path); u.banner_path = None
        c1, c2 = form.nick_cor.data or None, form.nick_cor2.data or None
        if (c1 and not u.pode_nick_cor) or (c2 and not u.pode_nick_gradiente):
            flash("Cor do nome faz parte dos planos pagos; as outras mudanças foram salvas.", "aviso")
        else:
            u.nick_cor = c1 if not c2 else None
            u.nick_gradiente = f"{c1},{c2}" if (c1 and c2) else None
        fonte = form.nick_fonte.data
        if fonte is not None and fonte not in {k for k, _ in FONTES}:
            fonte = ""  # valor fora da lista nunca é gravado
        if fonte and not u.pode("nick_fonte"):
            flash("Fonte do nome é um recurso do plano Avançado.", "aviso")
        elif fonte is not None:  # None = campo desabilitado/não enviado: mantém o atual
            u.nick_fonte = fonte or None
        tag = (form.tag_custom.data or "").strip()
        if tag and u.pode_tag_custom:
            if db.session.scalar(select(Usuario.id).where(Usuario.tag_custom == tag, Usuario.id != u.id)):
                flash("Essa tag já está em uso.", "erro")
            else:
                u.tag_custom = tag
        elif tag:
            flash("Tag personalizada é um recurso do plano Avançado.", "aviso")
        db.session.commit()
        flash("Perfil atualizado.", "sucesso")
        return redirect(url_for("perfil.configuracoes"))
    return render_template("perfil/configuracoes.html", form=form, senha=senha)


@bp.post("/configuracoes/senha")
@login_required
def alterar_senha():
    f = FormSenha(prefix="s")
    u = current_user
    if f.validate_on_submit():
        ok, msg = validar_senha(f.nova_senha.data, email=u.email, username=u.username)
        if not u.senha_hash:
            flash("Sua conta entra com Google e não tem senha. Use a recuperação de senha para criar uma.", "aviso")
        elif not bcrypt.check_password_hash(u.senha_hash, f.senha_atual.data):
            audit.registrar("senha_troca_falha", u.id, "senha atual incorreta", "falha", request=request)
            db.session.commit()
            flash("A senha atual está incorreta.", "erro")
        elif not ok:
            flash(msg, "erro")
        else:
            u.senha_hash = bcrypt.generate_password_hash(f.nova_senha.data).decode()
            u.session_version = (u.session_version or 0) + 1  # encerra as outras sessões
            session["sv"] = u.session_version
            login_user(u._get_current_object(), remember="remember_token" in request.cookies, fresh=True)  # renova o identificador (id:versão) só desta sessão
            audit.registrar("senha_alterada", u.id, request=request)
            db.session.commit()
            flash("Senha alterada. Os outros dispositivos foram desconectados.", "sucesso")
    else:
        flash("; ".join(e for es in f.errors.values() for e in es) or "Dados inválidos.", "erro")
    return redirect(url_for("perfil.configuracoes"))


@bp.get("/configuracoes/meus-dados")
@login_required
@limiter.limit("10 per hour")
def exportar_dados():
    import json
    from flask import Response
    corpo = json.dumps(conta.exportar(current_user), ensure_ascii=False, indent=2)
    audit.registrar("dados_exportados", current_user.id, request=request)
    db.session.commit()
    return Response(corpo, mimetype="application/json", headers={"Content-Disposition": "attachment; filename=exquest-meus-dados.json",
                                                                 "Cache-Control": "private, no-store"})


@bp.post("/configuracoes/excluir-conta")
@login_required
@limiter.limit("5 per hour")
def excluir_conta():
    u = current_user
    if request.form.get("confirmacao", "").strip().upper() != "EXCLUIR":
        flash("Digite EXCLUIR para confirmar.", "erro")
        return redirect(url_for("perfil.configuracoes"))
    if u.senha_hash and not bcrypt.check_password_hash(u.senha_hash, request.form.get("senha", "")):
        audit.registrar("conta_exclusao_falha", u.id, "senha incorreta", "falha", request=request)
        db.session.commit()
        flash("A senha está incorreta.", "erro")
        return redirect(url_for("perfil.configuracoes"))
    if not u.senha_hash and time.time() - session.get("login_ts", 0) > 600:  # sem senha para conferir: exige login dos últimos 10 min
        flash("Por segurança, entre novamente com o Google e tente de novo em até 10 minutos.", "erro")
        return redirect(url_for("perfil.configuracoes"))
    try:
        audit.registrar("conta_excluida", u.id, request=request)
        conta.excluir(u)
        db.session.commit()
    except conta.ErroConta as e:
        db.session.rollback()
        flash(str(e), "erro")
        return redirect(url_for("perfil.configuracoes"))
    logout_user()
    session.clear()
    flash("Sua conta foi excluída e seus dados pessoais foram removidos.", "sucesso")
    return redirect(url_for("main.inicio"))


MOTIVOS_DENUNCIA = {"ofensivo": "Conteúdo ofensivo", "falso": "Perfil falso ou golpe", "spam": "Spam ou propaganda", "outro": "Outro motivo"}


@bp.route("/perfil/<username>/denunciar", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def denunciar(username):
    alvo = db.session.scalar(select(Usuario).where(Usuario.username == username.lower(), Usuario.is_banido.is_(False)))
    if alvo is None:
        abort(404)
    motivo = request.form.get("motivo", "")
    if alvo.id == current_user.id or motivo not in MOTIVOS_DENUNCIA:
        flash("Não foi possível enviar a denúncia.", "erro")
        return redirect(url_for("perfil.ver", username=alvo.username))
    ja = db.session.scalar(select(Denuncia.id).where(
        Denuncia.autor_id == current_user.id, Denuncia.alvo_tipo == "usuario", Denuncia.alvo_id == alvo.id, Denuncia.status == "aberta"))
    if not ja:
        db.session.add(Denuncia(autor_id=current_user.id, alvo_tipo="usuario", alvo_id=alvo.id, motivo=motivo,
                                detalhe=limpar_texto(request.form.get("detalhe", ""), 500) or None))
        audit.registrar("denuncia_perfil", current_user.id, f"alvo={alvo.id} motivo={motivo}", request=request)
        db.session.commit()
    flash("Denúncia enviada. A equipe vai analisar.", "sucesso")  # mesma resposta com ou sem duplicata
    return redirect(url_for("perfil.ver", username=alvo.username))
