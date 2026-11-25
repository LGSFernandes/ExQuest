"""Mensagens: conversas diretas entre amigos e grupos. Atualização por polling (sem WebSocket)."""
from datetime import timedelta

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from app import clock
from app.blueprints.social import bp
from app.extensions import db, limiter
from app.models import Denuncia, GrupoChat, GrupoMembro, Mensagem, Usuario
from app.security import limpar_texto
from app.services import amizades, audit, chat as svc, uploads

MOTIVOS = {"ofensivo": "Conteúdo ofensivo", "spam": "Spam ou propaganda", "outro": "Outro motivo"}


def _grupo(gid) -> GrupoChat:
    g = db.session.get(GrupoChat, gid)
    if g is None or svc.membro(g.id, current_user.id) is None:
        abort(404)  # 404 também para quem não é membro: não revela que o grupo existe
    return g


def _json(m: Mensagem) -> dict:
    return {"id": m.id, "autor": m.remetente.nome if m.remetente else "?", "meu": m.remetente_id == current_user.id,
            "texto": m.conteudo or "", "hora": clock.para_local(m.enviado_em).strftime("%d/%m %H:%M"),
            "imagem": url_for("social.imagem", gid=m.grupo_id, nome=m.imagem_path) if m.imagem_path else None}


@bp.route("/mensagens")
@login_required
def chat():
    return render_template("social/chat.html", conversas=svc.conversas(current_user), amigos=amizades.amigos(current_user.id), max_membros=svc.MAX_MEMBROS)


@bp.post("/mensagens/direta/<int:uid>")
@login_required
def conversar(uid):
    try:
        g = svc.conversa_direta(current_user, uid)
        db.session.commit()
    except svc.ErroChat as e:
        db.session.rollback()
        flash(str(e), "erro")
        return redirect(url_for("social.amigos"))
    return redirect(url_for("social.conversa", gid=g.id))


@bp.post("/mensagens/grupos")
@login_required
@limiter.limit("10 per hour")
def criar_grupo():
    try:
        g = svc.criar_grupo(current_user, request.form.get("nome", ""), request.form.getlist("amigos", type=int))
        db.session.commit()
    except svc.ErroChat as e:
        db.session.rollback()
        flash(str(e), "erro")
        return redirect(url_for("social.chat"))
    return redirect(url_for("social.conversa", gid=g.id))


@bp.route("/mensagens/<int:gid>")
@login_required
def conversa(gid):
    g = _grupo(gid)
    dq = svc.desde(g, current_user.id)
    msgs = [_json(m) for m in svc.mensagens(g, desde_quando=dq)]  # antes do commit (ver `novas`)
    tem_antigas = len(msgs) >= svc.PAGINA and svc.anteriores(g, msgs[0]["id"], 1, desde_quando=dq)[1]
    svc.marcar_lida(current_user, g)
    db.session.commit()
    membros = list(db.session.scalars(select(Usuario).join(GrupoMembro, GrupoMembro.usuario_id == Usuario.id).where(GrupoMembro.grupo_id == g.id).order_by(GrupoMembro.id)))
    souadmin = bool(svc.membro(g.id, current_user.id).eh_admin)
    candidatos = [a for a in amizades.amigos(current_user.id) if a.id not in {u.id for u in membros}] if souadmin and not g.is_direto else []
    return render_template("social/conversa.html", g=g, titulo=svc.titulo(g, current_user.id), msgs=msgs, tem_antigas=tem_antigas, membros=membros,
                           candidatos=candidatos, souadmin=souadmin, motivos=MOTIVOS, max_texto=svc.MAX_TEXTO)


@bp.route("/mensagens/<int:gid>/anteriores")
@login_required
@limiter.limit("30 per minute")
def anteriores(gid):
    """Histórico paginado por cursor: `?antes=<id da mais antiga já exibida>`."""
    g = _grupo(gid)
    antes = request.args.get("antes", 0, type=int)
    if antes <= 0:
        abort(400)
    msgs, mais = svc.anteriores(g, antes, desde_quando=svc.desde(g, current_user.id))
    return jsonify(mensagens=[_json(m) for m in msgs], tem_mais=mais)


@bp.route("/mensagens/<int:gid>/novas")
@login_required
@limiter.limit("60 per minute")
def novas(gid):
    g = _grupo(gid)
    msgs = [_json(m) for m in svc.mensagens(g, depois=request.args.get("depois", 0, type=int), desde_quando=svc.desde(g, current_user.id))]  # serializa ANTES do commit: o commit expira os objetos e cada acesso viraria 1 consulta
    if msgs:
        svc.marcar_lida(current_user, g)
        db.session.commit()
    return jsonify(mensagens=msgs)


@bp.post("/mensagens/<int:gid>/enviar")
@login_required
@limiter.limit("30 per minute")
def enviar(gid):
    g = _grupo(gid)
    arquivo = request.files.get("imagem")
    nome = None
    try:
        if arquivo and arquivo.filename:
            recentes = db.session.scalar(select(func.count(Mensagem.id)).where(
                Mensagem.remetente_id == current_user.id, Mensagem.imagem_path.is_not(None),
                Mensagem.enviado_em > clock.agora() - timedelta(hours=1)))
            if recentes >= 20:
                raise svc.ErroChat("Limite de 20 imagens por hora no chat. Tente novamente mais tarde.")
            nome = uploads.salvar_imagem(arquivo, "chat", permitir_gif=current_user.pode("upload_gif"), privado=True, prefixo="c_")
        m = svc.enviar(current_user, g, request.form.get("texto", ""), nome)
        db.session.commit()
    except (svc.ErroChat, uploads.UploadInvalido) as e:
        db.session.rollback()
        if nome:
            uploads.remover("chat", nome, privado=True)
        return jsonify(erro=str(e)), 400
    return jsonify(mensagem=_json(m))


@bp.route("/mensagens/<int:gid>/imagem/<nome>")
@login_required
def imagem(gid, nome):
    g = _grupo(gid)
    consulta = select(Mensagem.id).where(Mensagem.grupo_id == g.id, Mensagem.imagem_path == nome, Mensagem.deletado.is_(False))
    dq = svc.desde(g, current_user.id)
    ok = db.session.scalar(consulta.where(Mensagem.enviado_em >= dq) if dq else consulta)  # mesma barreira de entrada do histórico
    caminho = uploads.caminho("chat", nome, privado=True) if ok else None
    if caminho is None:
        abort(404)
    r = send_file(caminho, max_age=0)
    r.headers["Cache-Control"] = "private, max-age=3600"  # nome aleatório; navegador reaproveita ao rolar a conversa
    return r


@bp.post("/mensagens/<int:gid>/sair")
@login_required
def sair(gid):
    g = _grupo(gid)
    try:
        svc.sair(current_user, g)
        db.session.commit()
        flash("Você saiu do grupo.", "sucesso")
    except svc.ErroChat as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(url_for("social.chat"))


@bp.post("/mensagens/<int:gid>/adicionar")
@login_required
def adicionar(gid):
    g = _grupo(gid)
    try:
        svc.adicionar(current_user, g, request.form.get("amigo", type=int) or 0)
        db.session.commit()
        flash("Pessoa adicionada.", "sucesso")
    except svc.ErroChat as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(url_for("social.conversa", gid=g.id))


@bp.post("/mensagens/<int:gid>/mensagem/<int:mid>/denunciar")
@login_required
@limiter.limit("20 per hour")
def denunciar_mensagem(gid, mid):
    g = _grupo(gid)
    m = db.session.get(Mensagem, mid)
    motivo = request.form.get("motivo", "")
    dq = svc.desde(g, current_user.id)
    if m is None or m.grupo_id != g.id or m.remetente_id == current_user.id or motivo not in MOTIVOS or (dq and m.enviado_em < dq):
        flash("Não foi possível enviar a denúncia.", "erro")
    else:
        if not db.session.scalar(select(Denuncia.id).where(Denuncia.autor_id == current_user.id, Denuncia.alvo_tipo == "mensagem",
                                                           Denuncia.alvo_id == m.id, Denuncia.status == "aberta")):
            db.session.add(Denuncia(autor_id=current_user.id, alvo_tipo="mensagem", alvo_id=m.id, motivo=motivo,
                                    detalhe=limpar_texto(request.form.get("detalhe", ""), 500) or None))
            audit.registrar("denuncia_mensagem", current_user.id, f"msg={m.id}", request=request)
            db.session.commit()
        flash("Denúncia enviada. A equipe vai analisar.", "sucesso")
    return redirect(url_for("social.conversa", gid=g.id))
