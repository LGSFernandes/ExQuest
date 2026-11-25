"""Carteira de moedas. Toda mudança de saldo passa por aqui e deixa um lançamento imutável no ledger.

Garantias:
    - atômico: o saldo é alterado por UPDATE condicional (`moedas >= valor` nos débitos), nunca por leitura+escrita;
    - idempotente: a `chave` é única; repetir a mesma operação devolve o lançamento original sem mexer no saldo;
    - auditável: `saldo_apos` em cada lançamento; `conferir()` compara ledger x saldo.
O chamador controla o commit (a operação faz parte da transação maior, ex.: compra = débito + inventário).
"""
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import LancamentoCarteira, Usuario


class SaldoInsuficiente(Exception):
    pass


class Lancamento:
    """Resultado de uma operação: `novo` é False quando a chave já existia (repetição ignorada)."""
    def __init__(self, lancamento: LancamentoCarteira, novo: bool):
        self.lancamento, self.novo = lancamento, novo

    @property
    def saldo(self) -> int:
        return self.lancamento.saldo_apos


def _por_chave(chave: str):
    return db.session.scalar(select(LancamentoCarteira).where(LancamentoCarteira.chave_idempotencia == chave))


def _aplicar(usuario_id: int, delta: int, categoria: str, chave: str, descricao, ref_tipo, ref_id, origem, por) -> Lancamento:
    if not isinstance(delta, int) or delta == 0:
        raise ValueError("valor da operação deve ser um inteiro diferente de zero")
    anterior = _por_chave(chave)
    if anterior is not None:
        return Lancamento(anterior, False)
    try:
        with db.session.begin_nested():  # se a chave colidir (corrida), o saldo também é revertido
            saldo_col = func.coalesce(Usuario.moedas, 0)
            stmt = update(Usuario).where(Usuario.id == usuario_id)
            if delta < 0:
                stmt = stmt.where(saldo_col >= -delta)
            res = db.session.execute(stmt.values(moedas=saldo_col + delta), execution_options={"synchronize_session": "fetch"})
            if res.rowcount == 0:
                if db.session.get(Usuario, usuario_id) is None:
                    raise ValueError("usuário inexistente")
                raise SaldoInsuficiente()
            saldo = db.session.scalar(select(Usuario.moedas).where(Usuario.id == usuario_id))
            lanc = LancamentoCarteira(
                usuario_id=usuario_id, tipo="credito" if delta > 0 else "debito", categoria=categoria, valor=abs(delta),
                saldo_apos=saldo, referencia_tipo=ref_tipo, referencia_id=None if ref_id is None else str(ref_id),
                chave_idempotencia=chave, descricao=(descricao or "")[:200] or None, origem=origem, criado_por_id=por)
            db.session.add(lanc)
            db.session.flush()
    except IntegrityError:
        anterior = _por_chave(chave)
        if anterior is None:
            raise
        return Lancamento(anterior, False)
    return Lancamento(lanc, True)


def creditar(usuario_id: int, valor: int, categoria: str, chave: str, *, descricao=None, ref_tipo=None, ref_id=None,
             origem="sistema", por=None) -> Lancamento:
    if valor <= 0:
        raise ValueError("crédito deve ser positivo")
    return _aplicar(usuario_id, valor, categoria, chave, descricao, ref_tipo, ref_id, origem, por)


def debitar(usuario_id: int, valor: int, categoria: str, chave: str, *, descricao=None, ref_tipo=None, ref_id=None,
            origem="sistema", por=None) -> Lancamento:
    """Levanta SaldoInsuficiente se o saldo não cobre `valor` (e nada é alterado)."""
    if valor <= 0:
        raise ValueError("débito deve ser positivo")
    return _aplicar(usuario_id, -valor, categoria, chave, descricao, ref_tipo, ref_id, origem, por)


def soma_ledger(usuario_id: int) -> int:
    v = db.session.scalar(select(func.coalesce(func.sum(
        case((LancamentoCarteira.tipo == "credito", LancamentoCarteira.valor), else_=-LancamentoCarteira.valor)), 0))
        .where(LancamentoCarteira.usuario_id == usuario_id))
    return int(v)


def conferir(usuario_id: int) -> tuple[bool, int, int]:
    """(consistente, saldo_do_usuario, soma_do_ledger)."""
    saldo = db.session.scalar(select(func.coalesce(Usuario.moedas, 0)).where(Usuario.id == usuario_id)) or 0
    soma = soma_ledger(usuario_id)
    return saldo == soma, saldo, soma
