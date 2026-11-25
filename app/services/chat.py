"""Conversas diretas (só entre amigos) e grupos. As regras de acesso vivem aqui."""
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, load_only

from app import clock
from app.extensions import db
from app.models import GrupoChat, GrupoMembro, Mensagem, Usuario
from app.security import limpar_texto
from app.services import amizades, notificacoes, uploads

MAX_TEXTO = 2000
MAX_MEMBROS = 20
PAGINA = 50


class ErroChat(Exception):
    pass


def membro(grupo_id: int, uid: int) -> GrupoMembro | None:
    return db.session.scalar(select(GrupoMembro).where(GrupoMembro.grupo_id == grupo_id, GrupoMembro.usuario_id == uid))


def _outro_do_direto(grupo: GrupoChat, uid: int) -> Usuario | None:
    m = db.session.scalar(select(GrupoMembro).where(GrupoMembro.grupo_id == grupo.id, GrupoMembro.usuario_id != uid))
    return db.session.get(Usuario, m.usuario_id) if m else None


def titulo(grupo: GrupoChat, uid: int) -> str:
    if grupo.is_direto:
        o = _outro_do_direto(grupo, uid)
        return o.nome if o else "Conversa"
    return grupo.nome


def conversa_direta(eu: Usuario, amigo_id: int) -> GrupoChat:
    if not amizades.sao_amigos(eu.id, amigo_id):
        raise ErroChat("Só é possível conversar com amigos.")
    meus = select(GrupoMembro.grupo_id).where(GrupoMembro.usuario_id == eu.id)
    g = db.session.scalar(select(GrupoChat).join(GrupoMembro, GrupoMembro.grupo_id == GrupoChat.id).where(
        GrupoChat.is_direto.is_(True), GrupoChat.id.in_(meus), GrupoMembro.usuario_id == amigo_id))
    if g is None:
        g = GrupoChat(nome="direto", criador_id=eu.id, is_direto=True)
        g.membros.append(GrupoMembro(usuario_id=eu.id, eh_admin=True))
        g.membros.append(GrupoMembro(usuario_id=amigo_id))
        db.session.add(g)
        db.session.flush()
    return g


def criar_grupo(eu: Usuario, nome: str, amigos_ids: list[int]) -> GrupoChat:
    nome = limpar_texto(nome, 100)
    ids = {i for i in amigos_ids if i != eu.id}
    if not nome:
        raise ErroChat("Dê um nome ao grupo.")
    if not ids:
        raise ErroChat("Escolha ao menos um amigo.")
    if len(ids) + 1 > MAX_MEMBROS:
        raise ErroChat(f"Um grupo comporta até {MAX_MEMBROS} pessoas.")
    teto = eu.limite("grupos")
    criados = db.session.scalar(select(func.count()).select_from(GrupoChat).where(GrupoChat.criador_id == eu.id, GrupoChat.is_direto.is_(False))) or 0
    if teto is not None and criados >= teto:
        raise ErroChat("Você atingiu o limite de grupos do seu plano.")
    if any(not amizades.sao_amigos(eu.id, i) for i in ids):
        raise ErroChat("Só é possível adicionar amigos ao grupo.")
    convidados = sorted(ids)
    if any(amizades.bloqueado_entre(a, b) for n, a in enumerate(convidados) for b in convidados[n + 1:]):
        raise ErroChat("Não foi possível criar o grupo com essas pessoas.")  # bloqueio entre convidados: mesma regra de adicionar()
    g = GrupoChat(nome=nome, criador_id=eu.id, icone_chave="users")
    g.membros.append(GrupoMembro(usuario_id=eu.id, eh_admin=True))
    for i in ids:
        g.membros.append(GrupoMembro(usuario_id=i))
    db.session.add(g)
    db.session.flush()
    for i in ids:
        notificacoes.criar(i, "chat", "Você foi adicionado a um grupo", f"{eu.nome} adicionou você em {nome}.", f"/mensagens/{g.id}", origem_id=eu.id)
    return g


def sair(eu: Usuario, grupo: GrupoChat) -> None:
    m = membro(grupo.id, eu.id)
    if m is None or grupo.is_direto:
        raise ErroChat("Conversa não encontrada.")
    db.session.delete(m)
    db.session.flush()
    resto = list(db.session.scalars(select(GrupoMembro).where(GrupoMembro.grupo_id == grupo.id).order_by(GrupoMembro.id)))
    if not resto:
        for msg in grupo.mensagens:
            uploads.remover_apos_commit("chat", msg.imagem_path, privado=True)
        db.session.delete(grupo)
    elif not any(r.eh_admin for r in resto):
        resto[0].eh_admin = True


def adicionar(eu: Usuario, grupo: GrupoChat, amigo_id: int) -> None:
    m = membro(grupo.id, eu.id)
    if m is None or not m.eh_admin or grupo.is_direto:
        raise ErroChat("Só administradores do grupo podem adicionar pessoas.")
    if not amizades.sao_amigos(eu.id, amigo_id):
        raise ErroChat("Só é possível adicionar amigos ao grupo.")
    if membro(grupo.id, amigo_id):
        raise ErroChat("Essa pessoa já está no grupo.")
    atuais = db.session.scalars(select(GrupoMembro.usuario_id).where(GrupoMembro.grupo_id == grupo.id)).all()
    if any(amizades.bloqueado_entre(amigo_id, uid) for uid in atuais):
        raise ErroChat("Não foi possível adicionar essa pessoa ao grupo.")  # não revela quem bloqueou quem
    if db.session.scalar(select(func.count()).select_from(GrupoMembro).where(GrupoMembro.grupo_id == grupo.id)) >= MAX_MEMBROS:
        raise ErroChat(f"Um grupo comporta até {MAX_MEMBROS} pessoas.")
    db.session.add(GrupoMembro(grupo_id=grupo.id, usuario_id=amigo_id))
    notificacoes.criar(amigo_id, "chat", "Você foi adicionado a um grupo", f"{eu.nome} adicionou você em {grupo.nome}.", f"/mensagens/{grupo.id}", origem_id=eu.id)


def _pode_falar(eu: Usuario, grupo: GrupoChat) -> None:
    if membro(grupo.id, eu.id) is None:
        raise ErroChat("Conversa não encontrada.")
    if grupo.is_direto:
        o = _outro_do_direto(grupo, eu.id)
        if o is None or o.is_banido or not amizades.sao_amigos(eu.id, o.id):
            raise ErroChat("Esta conversa não está mais disponível (amizade desfeita ou bloqueio).")


def enviar(eu: Usuario, grupo: GrupoChat, texto: str, imagem: str | None = None) -> Mensagem:
    _pode_falar(eu, grupo)
    if len(texto or "") > MAX_TEXTO:
        raise ErroChat(f"A mensagem passa de {MAX_TEXTO} caracteres.")  # recusa em vez de cortar em silêncio
    texto = limpar_texto(texto or "", MAX_TEXTO, True)
    if not texto and not imagem:
        raise ErroChat("Escreva uma mensagem ou envie uma imagem.")
    m = Mensagem(grupo_id=grupo.id, remetente_id=eu.id, conteudo=texto or None, imagem_path=imagem, tipo="imagem" if imagem else "texto")
    db.session.add(m)
    mm = membro(grupo.id, eu.id)
    mm.ultima_atividade = clock.agora()
    db.session.flush()
    return m


_COM_AUTOR = joinedload(Mensagem.remetente).load_only(Usuario.id, Usuario.nome)  # 1 consulta só, sem trazer o resto do usuário


def desde(grupo: GrupoChat, uid: int):
    """Em grupo, quem entra depois não lê o que foi dito antes de entrar. Conversa direta não tem essa barreira."""
    if grupo.is_direto:
        return None
    m = membro(grupo.id, uid)
    return m.entrou_em if m else None


def _recorte(q, grupo: GrupoChat, desde_quando):
    return q.where(Mensagem.enviado_em >= desde_quando) if desde_quando else q


def anteriores(grupo: GrupoChat, antes: int, limite: int = PAGINA, desde_quando=None) -> tuple[list[Mensagem], bool]:
    """Página de mensagens mais antigas que `antes` (cursor por id, não por offset: não repete nem pula itens se chegar mensagem nova).
    Devolve (em ordem cronológica, existem_mais_antigas)."""
    ult = list(db.session.scalars(_recorte(select(Mensagem).options(_COM_AUTOR).where(
        Mensagem.grupo_id == grupo.id, Mensagem.id < antes, Mensagem.deletado.is_(False)), grupo, desde_quando).order_by(Mensagem.id.desc()).limit(limite + 1)))
    return ult[:limite][::-1], len(ult) > limite


def mensagens(grupo: GrupoChat, depois: int = 0, limite: int = PAGINA, desde_quando=None) -> list[Mensagem]:
    """Em ordem cronológica. Sem `depois`, devolve as últimas `limite`."""
    if depois:
        return list(db.session.scalars(_recorte(select(Mensagem).options(_COM_AUTOR).where(
            Mensagem.grupo_id == grupo.id, Mensagem.id > depois, Mensagem.deletado.is_(False)), grupo, desde_quando).order_by(Mensagem.id).limit(limite)))
    ult = list(db.session.scalars(_recorte(select(Mensagem).options(_COM_AUTOR).where(Mensagem.grupo_id == grupo.id, Mensagem.deletado.is_(False)), grupo, desde_quando)
                                  .order_by(Mensagem.id.desc()).limit(limite)))
    return ult[::-1]


def marcar_lida(eu: Usuario, grupo: GrupoChat) -> None:
    m = membro(grupo.id, eu.id)
    if m:
        m.ultima_atividade = clock.agora()


def conversas(eu: Usuario) -> list[dict]:
    """Conversas do usuário, mais recentes primeiro, com contagem de não lidas. Consultas em lote: o custo não cresce com o nº de conversas."""
    meus = list(db.session.scalars(select(GrupoMembro).options(joinedload(GrupoMembro.grupo)).where(GrupoMembro.usuario_id == eu.id)))
    if not meus:
        return []
    ids = [m.grupo_id for m in meus]
    # em grupo, só conta o que foi dito depois da entrada (mesma regra de desde()); conversa direta não tem barreira
    visivel = or_(GrupoChat.is_direto.is_(True), Mensagem.enviado_em >= GrupoMembro.entrou_em)
    ult_ids = (select(func.max(Mensagem.id)).join(GrupoChat, GrupoChat.id == Mensagem.grupo_id)
               .join(GrupoMembro, (GrupoMembro.grupo_id == Mensagem.grupo_id) & (GrupoMembro.usuario_id == eu.id))
               .where(Mensagem.grupo_id.in_(ids), Mensagem.deletado.is_(False), visivel).group_by(Mensagem.grupo_id))
    ultimas = {m.grupo_id: m for m in db.session.scalars(select(Mensagem).where(Mensagem.id.in_(ult_ids)))}
    nao_lidas = dict(db.session.execute(
        select(Mensagem.grupo_id, func.count()).join(GrupoMembro, (GrupoMembro.grupo_id == Mensagem.grupo_id) & (GrupoMembro.usuario_id == eu.id))
        .join(GrupoChat, GrupoChat.id == Mensagem.grupo_id)
        .where(Mensagem.grupo_id.in_(ids), Mensagem.remetente_id != eu.id, Mensagem.deletado.is_(False), visivel,
               Mensagem.enviado_em > func.coalesce(GrupoMembro.ultima_atividade, GrupoChat.criado_em)).group_by(Mensagem.grupo_id)).all())
    diretos = [m.grupo_id for m in meus if m.grupo.is_direto]
    outros = {}
    if diretos:
        for gid, nome in db.session.execute(select(GrupoMembro.grupo_id, Usuario.nome).join(Usuario, Usuario.id == GrupoMembro.usuario_id)
                                            .where(GrupoMembro.grupo_id.in_(diretos), GrupoMembro.usuario_id != eu.id)):
            outros.setdefault(gid, nome)
    out = []
    for m in meus:
        g, ult = m.grupo, ultimas.get(m.grupo_id)
        if g.is_direto and ult is None:
            continue  # conversa vazia ainda não aparece na lista
        out.append({"grupo": g, "titulo": (outros.get(g.id) or "Conversa") if g.is_direto else g.nome, "ultima": ult, "nao_lidas": nao_lidas.get(g.id, 0)})
    out.sort(key=lambda c: (c["ultima"].enviado_em if c["ultima"] else c["grupo"].criado_em), reverse=True)
    return out
