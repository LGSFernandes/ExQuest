"""Coleções de questões do aluno. "Favoritos" é uma coleção especial, criada sob demanda."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Colecao, ColecaoItem, Questao

MAX_COLECOES = 100  # teto técnico quando o plano é ilimitado
MAX_ITENS = 500


class ErroColecao(Exception):
    pass


def favoritos(usuario_id: int) -> Colecao:
    c = db.session.scalar(select(Colecao).where(Colecao.usuario_id == usuario_id, Colecao.eh_favoritos.is_(True)))
    if c is None:
        try:
            with db.session.begin_nested():
                c = Colecao(usuario_id=usuario_id, nome="Favoritos", eh_favoritos=True)
                db.session.add(c)
        except IntegrityError:  # duas requisições criando ao mesmo tempo
            c = db.session.scalar(select(Colecao).where(Colecao.usuario_id == usuario_id, Colecao.nome == "Favoritos"))
    return c


def listar(usuario_id: int):
    favoritos(usuario_id)
    return db.session.execute(
        select(Colecao, func.count(ColecaoItem.id)).outerjoin(ColecaoItem, ColecaoItem.colecao_id == Colecao.id)
        .where(Colecao.usuario_id == usuario_id).group_by(Colecao.id).order_by(Colecao.eh_favoritos.desc(), Colecao.nome)).all()


def criar(usuario, nome: str) -> Colecao:
    usuario_id = usuario.id
    nome = " ".join((nome or "").split())
    if not 1 <= len(nome) <= 80:
        raise ErroColecao("Dê um nome de até 80 caracteres.")
    teto = usuario.limite("colecoes")
    teto = MAX_COLECOES if teto is None else min(teto, MAX_COLECOES)
    if db.session.scalar(select(func.count()).select_from(Colecao).where(
            Colecao.usuario_id == usuario_id, Colecao.eh_favoritos.is_(False))) >= teto:
        raise ErroColecao(f"Seu plano permite {teto} coleções além dos Favoritos. Veja os planos Premium para ter mais.")
    if db.session.scalar(select(Colecao.id).where(Colecao.usuario_id == usuario_id, func.lower(Colecao.nome) == nome.lower())):
        raise ErroColecao("Você já tem uma coleção com esse nome.")
    c = Colecao(usuario_id=usuario_id, nome=nome)
    db.session.add(c)
    db.session.flush()
    return c


def da_pessoa(usuario_id: int, colecao_id: int):
    return db.session.scalar(select(Colecao).where(Colecao.id == colecao_id, Colecao.usuario_id == usuario_id))


def definir(usuario_id: int, colecao_id: int, questao_id: int, presente: bool) -> bool:
    """Coloca ou tira a questão da coleção. Só mexe em coleção do próprio usuário. Idempotente."""
    c = da_pessoa(usuario_id, colecao_id)
    q = db.session.get(Questao, questao_id)
    if c is None or q is None or not q.ativo:
        raise ErroColecao("Coleção ou questão não encontrada.")
    item = db.session.scalar(select(ColecaoItem).where(ColecaoItem.colecao_id == c.id, ColecaoItem.questao_id == q.id))
    if presente and item is None:
        if db.session.scalar(select(func.count()).select_from(ColecaoItem).where(ColecaoItem.colecao_id == c.id)) >= MAX_ITENS:
            raise ErroColecao(f"Cada coleção comporta até {MAX_ITENS} questões.")
        try:
            with db.session.begin_nested():
                db.session.add(ColecaoItem(colecao_id=c.id, questao_id=q.id))
        except IntegrityError:
            pass  # já inserida por outra requisição
    elif not presente and item is not None:
        db.session.delete(item)
    return presente


def ids_da_questao(usuario_id: int, questao_id: int) -> set[int]:
    return set(db.session.scalars(select(ColecaoItem.colecao_id).join(Colecao).where(
        Colecao.usuario_id == usuario_id, ColecaoItem.questao_id == questao_id)))
