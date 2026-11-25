"""Amizades e bloqueios. Todas as regras ficam aqui; as rotas só traduzem erros em mensagens."""
from sqlalchemy import and_, delete, func, or_, select

from app.extensions import db
from app.models import Amizade, Bloqueio, Usuario
from app.services import notificacoes

MSG_GENERICA = "Não foi possível enviar o pedido a este usuário."  # não revela se a conta existe, bloqueou ou recusou


class ErroSocial(Exception):
    pass


def _par(a: int, b: int):
    return select(Amizade).where(or_(and_(Amizade.solicitante_id == a, Amizade.destinatario_id == b),
                                     and_(Amizade.solicitante_id == b, Amizade.destinatario_id == a)))


def relacao(a: int, b: int) -> Amizade | None:
    return db.session.scalar(_par(a, b))


def bloqueado_entre(a: int, b: int) -> bool:
    return db.session.scalar(select(Bloqueio.id).where(or_(
        and_(Bloqueio.bloqueador_id == a, Bloqueio.bloqueado_id == b),
        and_(Bloqueio.bloqueador_id == b, Bloqueio.bloqueado_id == a))).limit(1)) is not None


def sao_amigos(a: int, b: int) -> bool:
    r = relacao(a, b)
    return r is not None and r.status == "aceito" and not bloqueado_entre(a, b)


def total_amigos(uid: int) -> int:
    return db.session.scalar(select(func.count()).select_from(Amizade).where(
        Amizade.status == "aceito", or_(Amizade.solicitante_id == uid, Amizade.destinatario_id == uid))) or 0


def _teto(u: Usuario) -> int:
    t = u.limite("amigos")
    return 10_000 if t is None else t


def buscar(termo: str) -> Usuario | None:
    """Aceita `username` ou `username#tag` (tag numérica ou personalizada)."""
    termo = (termo or "").strip().lstrip("@").lower()
    if not termo or len(termo) > 60:
        return None
    nome, _, tag = termo.partition("#")
    q = select(Usuario).where(Usuario.username == nome, Usuario.is_banido.is_(False))
    if tag:
        q = q.where(or_(func.lower(Usuario.tag) == tag, func.lower(Usuario.tag_custom) == tag))
    return db.session.scalar(q)


def pedir(eu: Usuario, alvo: Usuario | None) -> str:
    """Devolve "enviado" ou "aceito" (quando o outro já tinha pedido o mesmo)."""
    if alvo is None or alvo.id == eu.id or bloqueado_entre(eu.id, alvo.id) or alvo.bloquear_pedidos_amizade:
        raise ErroSocial(MSG_GENERICA)
    r = relacao(eu.id, alvo.id)
    if r is not None:
        if r.status == "aceito":
            raise ErroSocial("Vocês já são amigos.")
        if r.status == "pendente" and r.destinatario_id == eu.id:
            aceitar(eu, r)
            return "aceito"
        if r.status == "pendente":
            raise ErroSocial("Você já enviou um pedido para esta pessoa.")
        if r.destinatario_id != eu.id:
            raise ErroSocial(MSG_GENERICA)  # recusado: quem foi recusado não insiste
        db.session.delete(r)  # quem recusou pode mudar de ideia e pedir
        db.session.flush()
    if total_amigos(eu.id) >= _teto(eu):
        raise ErroSocial("Você atingiu o limite de amigos do seu plano.")
    db.session.add(Amizade(solicitante_id=eu.id, destinatario_id=alvo.id, status="pendente"))
    notificacoes.criar(alvo.id, "amizade", "Novo pedido de amizade", f"{eu.nome} quer ser seu amigo.", "/amigos", origem_id=eu.id)
    return "enviado"


def aceitar(eu: Usuario, r: Amizade) -> None:
    if r.destinatario_id != eu.id or r.status != "pendente":
        raise ErroSocial("Pedido não encontrado.")
    if total_amigos(eu.id) >= _teto(eu):
        raise ErroSocial("Você atingiu o limite de amigos do seu plano.")
    outro = db.session.get(Usuario, r.solicitante_id)
    if outro is None or outro.is_banido or bloqueado_entre(eu.id, outro.id) or total_amigos(outro.id) >= _teto(outro):
        raise ErroSocial("Não foi possível aceitar este pedido.")
    r.status = "aceito"
    notificacoes.criar(outro.id, "amizade", "Pedido aceito", f"{eu.nome} aceitou seu pedido de amizade.", "/amigos", origem_id=eu.id)


def recusar(eu: Usuario, r: Amizade) -> None:
    if r.destinatario_id != eu.id or r.status != "pendente":
        raise ErroSocial("Pedido não encontrado.")
    r.status = "recusado"


def desfazer(eu: Usuario, r: Amizade) -> None:
    """Remove amizade aceita (qualquer lado) ou cancela pedido pendente enviado por mim."""
    if eu.id not in (r.solicitante_id, r.destinatario_id):
        raise ErroSocial("Pedido não encontrado.")
    if r.status == "pendente" and r.solicitante_id != eu.id:
        raise ErroSocial("Use recusar para pedidos recebidos.")
    db.session.delete(r)


def bloquear(eu: Usuario, alvo: Usuario) -> None:
    if alvo.id == eu.id:
        raise ErroSocial("Não é possível bloquear a si mesmo.")
    if not db.session.scalar(select(Bloqueio.id).where(Bloqueio.bloqueador_id == eu.id, Bloqueio.bloqueado_id == alvo.id)):
        db.session.add(Bloqueio(bloqueador_id=eu.id, bloqueado_id=alvo.id))
    db.session.execute(delete(Amizade).where(or_(and_(Amizade.solicitante_id == eu.id, Amizade.destinatario_id == alvo.id),
                                                 and_(Amizade.solicitante_id == alvo.id, Amizade.destinatario_id == eu.id))))


def desbloquear(eu: Usuario, alvo_id: int) -> None:
    db.session.execute(delete(Bloqueio).where(Bloqueio.bloqueador_id == eu.id, Bloqueio.bloqueado_id == alvo_id))


def amigos(uid: int) -> list[Usuario]:
    ids = [a.destinatario_id if a.solicitante_id == uid else a.solicitante_id for a in db.session.scalars(
        select(Amizade).where(Amizade.status == "aceito", or_(Amizade.solicitante_id == uid, Amizade.destinatario_id == uid)))]
    if not ids:
        return []
    bloqueados = {b.bloqueado_id if b.bloqueador_id == uid else b.bloqueador_id for b in db.session.scalars(
        select(Bloqueio).where(or_(Bloqueio.bloqueador_id == uid, Bloqueio.bloqueado_id == uid)))}
    return list(db.session.scalars(select(Usuario).where(Usuario.id.in_(set(ids) - bloqueados), Usuario.is_banido.is_(False))
                                   .order_by(Usuario.nome)))


def recebidos(uid: int):
    return db.session.scalars(select(Amizade).where(Amizade.destinatario_id == uid, Amizade.status == "pendente").order_by(Amizade.id.desc())).all()


def enviados(uid: int):
    return db.session.scalars(select(Amizade).where(Amizade.solicitante_id == uid, Amizade.status == "pendente").order_by(Amizade.id.desc())).all()


def bloqueados(uid: int) -> list[Usuario]:
    return list(db.session.scalars(select(Usuario).join(Bloqueio, Bloqueio.bloqueado_id == Usuario.id).where(Bloqueio.bloqueador_id == uid)))
