"""Administração: cadastro de questões com preview LaTeX ao vivo. Toda rota exige admin."""
import json
from datetime import date

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, load_only

from app import clock, web
from app.extensions import db
from app.forms.admin import FormMateria, FormQuestao
from app.models import Alternativa, Denuncia, Materia, Mensagem, Questao, RespostaUsuario, Torneio, Usuario
from app.models.competition import TORNEIO_CONFIG
from app.security import admin_required, limpar_texto
from app.services import audit, competicoes, destaques, rum, uploads

bp = Blueprint("admin", __name__, url_prefix="/admin")
POR_PAGINA = 20
MAX_ALT = 6


@bp.before_request
@login_required
@admin_required
def _so_admin():
    pass


@bp.route("/")
def painel():
    total = db.session.scalar(select(func.count(Questao.id)))
    ativas = db.session.scalar(select(func.count(Questao.id)).where(Questao.ativo.is_(True)))
    return render_template("admin/painel.html", total=total, ativas=ativas)


@bp.route("/questoes")
def questoes():
    q = request.args.get("q", "").strip()[:100]
    materia_id = request.args.get("materia_id", type=int)
    sel = select(Questao).order_by(Questao.id.desc())
    if q:
        sel = sel.where(Questao.enunciado.ilike(f"%{q.replace('%', '').replace('_', '')}%"))
    if materia_id:
        sel = sel.where(Questao.materia_id == materia_id)
    sel = sel.options(joinedload(Questao.materia).load_only(Materia.id, Materia.nome),
                      load_only(Questao.id, Questao.enunciado, Questao.dificuldade, Questao.ativo, Questao.materia_id))  # a lista não usa explicação/gabarito
    pag = db.paginate(sel, page=request.args.get("page", 1, type=int), per_page=POR_PAGINA, error_out=False)
    materias = db.session.scalars(select(Materia).order_by(Materia.nome)).all()
    return web.pagina_ou_fragmento("admin/questoes.html", "admin/_questoes_lista.html", pag=pag, materias=materias, q=q, materia_id=materia_id)


def _alternativas_do_form() -> list[tuple[str, bool]]:
    textos = [limpar_texto(t, 1000, True) for t in request.form.getlist("alt_texto")[:MAX_ALT]]
    certa = request.form.get("alt_correta", type=int)
    return [(t, i == certa) for i, t in enumerate(textos) if t]


def _validar_multipla(alts: list[tuple[str, bool]]) -> str | None:
    if len(alts) < 2:
        return "Informe ao menos duas alternativas."
    if sum(c for _, c in alts) != 1:
        return "Marque exatamente uma alternativa correta."
    return None


def _salvar(form: FormQuestao, questao: Questao | None):
    nova = questao is None
    questao = questao or Questao()
    alts = _alternativas_do_form()
    if form.tipo.data == "multipla":
        erro = _validar_multipla(alts)
        if erro:
            flash(erro, "erro")
            return None
    questao.materia_id, questao.dificuldade, questao.tipo = form.materia_id.data, form.dificuldade.data, form.tipo.data
    questao.conteudo = limpar_texto(form.conteudo.data, 100) or None
    questao.enunciado = limpar_texto(form.enunciado.data, 5000, True)
    questao.explicacao = limpar_texto(form.explicacao.data, 5000, True) or None
    questao.resposta_correta = limpar_texto(form.resposta_correta.data, 5000, True) or None
    questao.ativo = form.ativo.data
    apagar_apos_commit, nova_imagem = [], None  # arquivos só somem depois que o banco confirma
    try:
        if form.remover_imagem.data and questao.imagem_path:
            apagar_apos_commit.append(questao.imagem_path)
            questao.imagem_path = None
        if form.imagem.data and getattr(form.imagem.data, "filename", ""):
            if questao.imagem_path:
                apagar_apos_commit.append(questao.imagem_path)
            nova_imagem = questao.imagem_path = uploads.salvar_imagem(form.imagem.data, "img_questao", permitir_gif=False)
    except uploads.UploadInvalido as e:
        flash(str(e), "erro")
        return None
    if form.tipo.data == "multipla" and not _sincronizar_alternativas(questao, alts):
        db.session.rollback()
        uploads.remover("img_questao", nova_imagem)
        flash("Não é possível remover uma alternativa que já foi escolhida por alunos. Edite o texto dela em vez disso.", "erro")
        return None
    if nova:
        db.session.add(questao)
    db.session.flush()
    audit.registrar("questao_criada" if nova else "questao_editada", current_user.id, f"q={questao.id}", request=request)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        uploads.remover("img_questao", nova_imagem)
        raise
    for nome in apagar_apos_commit:
        uploads.remover("img_questao", nome)
    return questao


def _sincronizar_alternativas(questao, alts) -> bool:
    """Edita por posição e preserva as linhas existentes: respostas antigas apontam para elas (FK)."""
    atuais = list(questao.alternativas)
    for a, (t, c) in zip(atuais, alts):
        a.texto, a.correta = t, c
    for t, c in alts[len(atuais):]:
        questao.alternativas.append(Alternativa(texto=t, correta=c))
    for a in atuais[len(alts):]:
        usada = a.id and db.session.scalar(select(func.count()).select_from(RespostaUsuario).where(RespostaUsuario.alternativa_id == a.id))
        if usada:
            return False
        questao.alternativas.remove(a)
    return True


def _form(questao: Questao | None):
    form = FormQuestao(obj=questao)
    form.materia_id.choices = [(m.id, m.nome) for m in db.session.scalars(select(Materia).order_by(Materia.nome))]
    return form


@bp.route("/questoes/nova", methods=["GET", "POST"])
def questao_nova():
    form = _form(None)
    if form.validate_on_submit() and _salvar(form, None):
        flash("Questão criada.", "sucesso")
        return redirect(url_for("admin.questoes"))
    return render_template("admin/questao_form.html", form=form, questao=None, alts=_alts_para_tela(None))


@bp.route("/questoes/<int:qid>/editar", methods=["GET", "POST"])
def questao_editar(qid):
    questao = db.session.get(Questao, qid) or abort(404)
    form = _form(questao)
    if form.validate_on_submit() and _salvar(form, questao):
        flash("Questão atualizada.", "sucesso")
        return redirect(url_for("admin.questoes"))
    return render_template("admin/questao_form.html", form=form, questao=questao, alts=_alts_para_tela(questao))


def _alts_para_tela(questao):
    if request.method == "POST":
        certa = request.form.get("alt_correta", type=int)
        itens = [(t, i == certa) for i, t in enumerate(request.form.getlist("alt_texto")[:MAX_ALT])]
    elif questao:
        itens = [(a.texto, a.correta) for a in questao.alternativas]
    else:
        itens = []
    return (itens + [("", False)] * 4)[:max(4, len(itens))]


# ---------- matérias ----------
@bp.route("/desempenho")
def desempenho():
    """p75 dos Core Web Vitals medidos no navegador dos alunos (RUM), por rota."""
    disp = request.args.get("d") if request.args.get("d") in rum.DISPOSITIVOS else None
    dias = request.args.get("dias", 7, type=int)
    dias = dias if dias in (1, 7, 30) else 7
    return render_template("admin/desempenho.html", linhas=rum.resumo(dias, disp), dias=dias, disp=disp, limites=rum.LIMITES)


@bp.route("/materias")
def materias():
    lista = db.session.execute(
        select(Materia, func.count(Questao.id)).outerjoin(Questao, Questao.materia_id == Materia.id)
        .group_by(Materia.id).order_by(Materia.nome)).all()
    return render_template("admin/materias.html", lista=lista)


def _salvar_materia(form: FormMateria, materia: Materia | None):
    nome = limpar_texto(form.nome.data, 100)
    existe = db.session.scalar(select(Materia).where(func.lower(Materia.nome) == nome.lower()))
    if existe and (materia is None or existe.id != materia.id):
        form.nome.errors.append("Já existe uma matéria com esse nome.")
        return None
    materia = materia or Materia()
    materia.nome, materia.icone_chave, materia.cor, materia.ativo = nome, form.icone_chave.data, form.cor.data, form.ativo.data
    db.session.add(materia)
    db.session.flush()
    audit.registrar("materia_salva", current_user.id, f"m={materia.id}", request=request)
    db.session.commit()
    destaques.materias_mudaram()
    return materia


@bp.route("/materias/nova", methods=["GET", "POST"])
def materia_nova():
    form = FormMateria()
    if form.validate_on_submit() and _salvar_materia(form, None):
        flash("Matéria criada.", "sucesso")
        return redirect(url_for("admin.materias"))
    return render_template("admin/materia_form.html", form=form, materia=None)


@bp.route("/materias/<int:mid>/editar", methods=["GET", "POST"])
def materia_editar(mid):
    materia = db.session.get(Materia, mid) or abort(404)
    form = FormMateria(obj=materia)
    if form.validate_on_submit() and _salvar_materia(form, materia):
        flash("Matéria atualizada.", "sucesso")
        return redirect(url_for("admin.materias"))
    return render_template("admin/materia_form.html", form=form, materia=materia)


# ---------- importação e exportação ----------
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ITENS = 500


def _questao_para_dict(q: Questao) -> dict:
    d = {"materia": q.materia.nome, "dificuldade": q.dificuldade, "tipo": q.tipo, "conteudo": q.conteudo,
         "enunciado": q.enunciado, "explicacao": q.explicacao, "ativo": bool(q.ativo)}
    if q.tipo == "discursiva":
        d["resposta_correta"] = q.resposta_correta
    else:
        d["alternativas"] = [{"texto": a.texto, "correta": bool(a.correta)} for a in q.alternativas]
    return d


@bp.route("/questoes/exportar")
def questoes_exportar():
    """Exporta todas as questões (sem imagens). O arquivo pode ser reimportado."""
    qs = db.session.scalars(select(Questao).order_by(Questao.id)).all()
    corpo = json.dumps({"versao": 1, "questoes": [_questao_para_dict(q) for q in qs]}, ensure_ascii=False, indent=1)
    return Response(corpo, mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="exquest-questoes-{date.today().isoformat()}.json"'})


def _validar_item(i: int, d, materias: dict) -> tuple[dict | None, str | None]:
    if not isinstance(d, dict):
        return None, f"item {i}: formato inválido"
    mat = materias.get(str(d.get("materia", "")).strip().lower())
    if mat is None:
        return None, f"item {i}: matéria '{str(d.get('materia', ''))[:40]}' não existe (cadastre antes em Matérias)"
    enun = limpar_texto(str(d.get("enunciado") or ""), 5000, True)
    dif, tipo = d.get("dificuldade", "medio"), d.get("tipo", "multipla")
    if not enun:
        return None, f"item {i}: enunciado vazio"
    if dif not in ("facil", "medio", "dificil") or tipo not in ("multipla", "discursiva"):
        return None, f"item {i}: dificuldade ou tipo inválido"
    item = {"materia_id": mat, "dificuldade": dif, "tipo": tipo, "enunciado": enun,
            "conteudo": limpar_texto(str(d.get("conteudo") or ""), 100) or None,
            "explicacao": limpar_texto(str(d.get("explicacao") or ""), 5000, True) or None,
            "ativo": bool(d.get("ativo", True)), "alts": [], "resposta_correta": None}
    if tipo == "discursiva":
        item["resposta_correta"] = limpar_texto(str(d.get("resposta_correta") or ""), 5000, True) or None
    else:
        raw = d.get("alternativas")
        if not isinstance(raw, list) or len(raw) > MAX_ALT:
            return None, f"item {i}: alternativas inválidas (2 a {MAX_ALT})"
        alts = [(limpar_texto(str(a.get("texto") or ""), 1000, True), bool(a.get("correta"))) for a in raw if isinstance(a, dict)]
        alts = [(t, c) for t, c in alts if t]
        erro = _validar_multipla(alts)
        if erro:
            return None, f"item {i}: {erro}"
        item["alts"] = alts
    return item, None


@bp.route("/questoes/importar", methods=["GET", "POST"])
def questoes_importar():
    relatorio = None
    if request.method == "POST":
        arq = request.files.get("arquivo")
        dados = arq.stream.read(MAX_IMPORT_BYTES + 1) if arq else b""
        erros, itens = [], []
        try:
            if not dados or len(dados) > MAX_IMPORT_BYTES:
                raise ValueError("Envie um arquivo JSON de até 2 MB.")
            doc = json.loads(dados.decode("utf-8"))
            lista = doc.get("questoes") if isinstance(doc, dict) else None
            if not isinstance(lista, list) or not lista or len(lista) > MAX_IMPORT_ITENS:
                raise ValueError(f"O arquivo deve ter de 1 a {MAX_IMPORT_ITENS} questões em \"questoes\".")
        except (ValueError, UnicodeDecodeError) as e:
            flash(str(e) if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else "Arquivo JSON inválido.", "erro")
            return render_template("admin/importar.html", relatorio=None), 400
        materias = {m.nome.lower(): m.id for m in db.session.scalars(select(Materia))}
        vistos = {(q.materia_id, q.enunciado) for q in db.session.execute(select(Questao.materia_id, Questao.enunciado))}
        duplicadas = 0
        for i, d in enumerate(lista, 1):
            item, erro = _validar_item(i, d, materias)
            if erro:
                erros.append(erro)
            elif (item["materia_id"], item["enunciado"]) in vistos:
                duplicadas += 1
            else:
                vistos.add((item["materia_id"], item["enunciado"]))
                itens.append(item)
        if erros:  # tudo ou nada: um erro cancela a importação inteira
            relatorio = {"ok": False, "erros": erros[:50], "total_erros": len(erros)}
            return render_template("admin/importar.html", relatorio=relatorio), 422
        for it in itens:
            alts = it.pop("alts")
            q = Questao(**it)
            q.alternativas = [Alternativa(texto=t, correta=c) for t, c in alts]
            db.session.add(q)
        audit.registrar("questoes_importadas", current_user.id, f"n={len(itens)}", request=request)
        db.session.commit()
        relatorio = {"ok": True, "importadas": len(itens), "duplicadas": duplicadas}
    return render_template("admin/importar.html", relatorio=relatorio)


# ---------- moderação ----------
@bp.route("/denuncias")
def denuncias():
    itens = db.session.scalars(select(Denuncia).order_by(Denuncia.status != "aberta", Denuncia.id.desc()).limit(200)).all()
    mensagens = {m.id: m for m in db.session.scalars(select(Mensagem).where(Mensagem.id.in_({d.alvo_id for d in itens if d.alvo_tipo == "mensagem"})))}
    ids = {d.alvo_id for d in itens if d.alvo_tipo == "usuario"} | {d.autor_id for d in itens} | {m.remetente_id for m in mensagens.values()}
    usuarios = {u.id: u for u in db.session.scalars(select(Usuario).where(Usuario.id.in_(ids)))} if ids else {}
    return render_template("admin/denuncias.html", itens=itens, usuarios=usuarios, mensagens=mensagens)


@bp.route("/denuncias/<int:did>/resolver", methods=["POST"])
def denuncia_resolver(did):
    d = db.session.get(Denuncia, did) or abort(404)
    acao = request.form.get("acao")
    if acao not in ("arquivar", "banir", "ocultar"):
        abort(400)
    if d.status != "aberta":
        flash("Esta denúncia já foi resolvida.", "aviso")
        return redirect(url_for("admin.denuncias"))
    novo = "arquivada"
    if acao == "ocultar":
        m = db.session.get(Mensagem, d.alvo_id) if d.alvo_tipo == "mensagem" else None
        if m is None:
            flash("Esta denúncia não é de uma mensagem.", "erro")
            return redirect(url_for("admin.denuncias"))
        m.deletado, novo = True, "procedente"
        audit.registrar("mensagem_oculta", current_user.id, f"msg={m.id} denuncia={d.id}", request=request)
    if acao == "banir":
        m = db.session.get(Mensagem, d.alvo_id) if d.alvo_tipo == "mensagem" else None
        if d.alvo_tipo == "usuario":
            alvo = db.session.get(Usuario, d.alvo_id)
        else:  # mensagem apagada: não dá para saber o autor, e alvo_id é id de mensagem (nunca de usuário)
            alvo = db.session.get(Usuario, m.remetente_id) if m else None
        if alvo is None or alvo.is_admin or alvo.id == current_user.id:
            flash("Esta denúncia não permite banir uma conta.", "erro")
            return redirect(url_for("admin.denuncias"))
        alvo.is_banido, novo = True, "procedente"
        audit.registrar("usuario_banido", current_user.id, f"alvo={alvo.id} denuncia={d.id}", request=request)
        for o in db.session.scalars(select(Denuncia).where(Denuncia.alvo_tipo == "usuario", Denuncia.alvo_id == alvo.id, Denuncia.status == "aberta")):
            o.status, o.resolvida_por_id, o.resolvida_em = "procedente", current_user.id, clock.agora()
    d.status, d.resolvida_por_id, d.resolvida_em = novo, current_user.id, clock.agora()
    audit.registrar("denuncia_resolvida", current_user.id, f"d={d.id} acao={acao}", request=request)
    db.session.commit()
    flash("Denúncia resolvida.", "sucesso")
    return redirect(url_for("admin.denuncias"))


# ---------- competições ----------
def _data_local(txt: str):
    from datetime import datetime
    try:
        return clock.local_para_utc(datetime.strptime(txt.strip(), "%Y-%m-%dT%H:%M"))
    except ValueError:
        return None


@bp.route("/competicoes")
def competicoes_lista():
    competicoes.encerrar_vencidos()
    db.session.commit()
    itens = db.session.scalars(select(Torneio).order_by(Torneio.inicio.desc()).limit(100)).all()
    return render_template("admin/competicoes.html", itens=itens, tipos=TORNEIO_CONFIG,
                           materias=destaques.materias_ativas())


@bp.post("/competicoes/nova")
def competicao_nova():
    f = request.form
    inicio, fim = _data_local(f.get("inicio", "")), _data_local(f.get("fim", ""))
    if not inicio or not fim:
        flash("Informe início e fim no formato de data e hora.", "erro")
        return redirect(url_for("admin.competicoes_lista"))
    ids = {m for m in (int(x) for x in f.getlist("materias") if x.isdigit())}
    ids &= set(db.session.scalars(select(Materia.id)))
    dific = [d for d in f.getlist("dificuldades") if d in ("facil", "medio", "dificil")]
    premios = {}
    for k in ("recompensa_xp_1", "recompensa_xp_2", "recompensa_xp_3", "recompensa_moedas_1", "recompensa_moedas_2", "recompensa_moedas_3"):
        v = f.get(k, "")
        if v.isdigit():
            premios[k] = int(v)
    try:
        t = competicoes.criar(nome=limpar_texto(f.get("nome", ""), 100), descricao=limpar_texto(f.get("descricao", ""), 1000, multilinha=True),
                              tipo=f.get("tipo", ""), materias=sorted(ids), dificuldades=dific, inicio=inicio, fim=fim, premios=premios)
        audit.registrar("competicao_criar", current_user.id, f"torneio {t.nome}", request=request)
        db.session.commit()
        flash("Competição criada.", "sucesso")
    except competicoes.ErroCompeticao as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(url_for("admin.competicoes_lista"))


@bp.post("/competicoes/<int:tid>/cancelar")
def competicao_cancelar(tid):
    t = db.session.get(Torneio, tid) or abort(404)
    try:
        competicoes.cancelar(t)
        audit.registrar("competicao_cancelar", current_user.id, f"torneio {t.id}", request=request)
        db.session.commit()
        flash("Competição cancelada.", "sucesso")
    except competicoes.ErroCompeticao as e:
        db.session.rollback()
        flash(str(e), "erro")
    return redirect(url_for("admin.competicoes_lista"))
