"""Pedidos de dinheiro real. Regra de ouro: só o webhook verificado (ou a reconciliação ativa) muda o status; a volta do
navegador nunca libera nada. A transição para 'aprovado' é um UPDATE condicional, então eventos duplicados ou
simultâneos entregam o produto UMA vez."""
import secrets

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app import clock
from app.extensions import db
from app.models import EventoWebhook, Pagamento, Usuario
from app.providers import mercadopago, stripe_provider
from app.providers.base import Notificacao, ProviderIndisponivel
from app.services import notificacoes, audit, premium, wallet
from app.services.plans import PLANOS

PROVEDORES = {"mercadopago": mercadopago, "stripe": stripe_provider}
NOME_PROVEDOR = {"mercadopago": "Mercado Pago (Pix, cartão, boleto)", "stripe": "Stripe (cartão)"}
PACOTES = {  # centavos de BRL
    "starter": {"nome": "Iniciante", "moedas": 180, "bonus": 20, "preco": 1190},
    "popular": {"nome": "Popular", "moedas": 400, "bonus": 50, "preco": 2490},
    "premium": {"nome": "Premium", "moedas": 1500, "bonus": 300, "preco": 14990},
    "ultimate": {"nome": "Ultimate", "moedas": 4000, "bonus": 750, "preco": 24990},
}
BONUS_PRIMEIRA = 1.0  # primeira compra de moedas aprovada dobra o bônus do pacote


def provedores_disponiveis() -> list[str]:
    return [k for k, m in PROVEDORES.items() if m.disponivel()]


def _primeira_compra(uid: int, ignorar_id: int | None = None) -> bool:
    q = select(Pagamento.id).where(Pagamento.usuario_id == uid, Pagamento.tipo == "moedas", Pagamento.status == "aprovado")
    if ignorar_id:
        q = q.where(Pagamento.id != ignorar_id)
    return db.session.scalar(q.limit(1)) is None


def criar_pedido(usuario: Usuario, tipo: str, produto: str, provider: str) -> Pagamento:
    if provider not in PROVEDORES or not PROVEDORES[provider].disponivel():
        raise ProviderIndisponivel("Esta forma de pagamento não está disponível agora.")
    if tipo == "moedas":
        p = PACOTES.get(produto)
        if not p:
            raise ValueError("Pacote inválido.")
        # o bônus de primeira compra é decidido na entrega (_entregar), não aqui: dois checkouts abertos não o recebem duas vezes
        total = p["moedas"] + p["bonus"]
        pg = Pagamento(tipo="moedas", produto_ref=produto, descricao=f"ExQuest — pacote {p['nome']}", valor_centavos=p["preco"],
                       moedas_total=total, bonus_primeira=False)
    elif tipo == "premium":
        plano, _, ciclo = produto.partition(":")
        premium.validar_compra(usuario, plano, ciclo)
        pg = Pagamento(tipo="premium", produto_ref=produto, descricao=f"ExQuest Premium {PLANOS[plano]['nome']} ({ciclo})",
                       valor_centavos=PLANOS[plano][ciclo], plano=plano, ciclo=ciclo)
    else:
        raise ValueError("Produto inválido.")
    pg.usuario_id, pg.provider, pg.chave_idempotencia = usuario.id, provider, secrets.token_urlsafe(24)
    db.session.add(pg)
    db.session.flush()
    try:
        pg.provider_ref, url = PROVEDORES[provider].criar_checkout(pg, usuario.email)
    except ProviderIndisponivel:
        pg.status, pg.observacao = "cancelado", "falha ao criar checkout"
        db.session.commit()
        raise
    pg.status = "pendente"
    audit.registrar("pagamento_criado", usuario.id, f"pg={pg.id} {provider} {pg.produto_ref}")
    db.session.commit()
    pg._url = url
    return pg


def _entregar(pg: Pagamento) -> None:
    u = db.session.get(Usuario, pg.usuario_id)
    if pg.tipo == "moedas":
        p = PACOTES.get(pg.produto_ref)
        if p and _primeira_compra(u.id, pg.id):
            pg.moedas_total += int(p["bonus"] * BONUS_PRIMEIRA)
            pg.bonus_primeira = True
            pg.descricao = f"{pg.descricao} (+ bônus de primeira compra)"
        wallet.creditar(u.id, pg.moedas_total, "compra_moedas", f"pagamento:{pg.id}", descricao=pg.descricao, ref_tipo="pagamento", ref_id=pg.id)
    else:
        premium.ativar(u, pg.plano, pg.ciclo, pg)
    audit.registrar("pagamento_aprovado", u.id, f"pg={pg.id} {pg.provider}")
    notificacoes.criar(u.id, "pagamento", "Pagamento confirmado", pg.descricao, "/loja/moedas" if pg.tipo == "moedas" else "/premium")


def _estornar(pg: Pagamento) -> None:
    u = db.session.get(Usuario, pg.usuario_id)
    if pg.tipo == "moedas":
        saldo = db.session.scalar(select(Usuario.moedas).where(Usuario.id == u.id)) or 0
        retirar = min(saldo, pg.moedas_total)  # moedas já gastas não geram saldo negativo
        if retirar:
            wallet.debitar(u.id, retirar, "estorno", f"estorno:{pg.id}", descricao="Estorno de pagamento", ref_tipo="pagamento", ref_id=pg.id)
        if retirar < pg.moedas_total:
            pg.observacao = f"estorno parcial: {retirar} de {pg.moedas_total} moedas (o resto já foi gasto)"
    else:
        premium.revogar(u, pg)
    audit.registrar("pagamento_estornado", u.id, f"pg={pg.id}", "alerta")
    notificacoes.criar(u.id, "pagamento", "Pagamento estornado", pg.descricao, "/loja/moedas" if pg.tipo == "moedas" else "/premium")


def aplicar(n: Notificacao, provider: str) -> str:
    """Aplica uma notificação já verificada. Devolve um rótulo de resultado (vai para eventos_webhook)."""
    pg = None
    if n.pagamento_id and str(n.pagamento_id).isdigit():
        pg = db.session.get(Pagamento, int(n.pagamento_id))
    if pg is None and n.provider_payment_id:
        pg = db.session.scalar(select(Pagamento).where(Pagamento.provider == provider, Pagamento.provider_payment_id == n.provider_payment_id))
    if pg is None or pg.provider != provider:
        return "pedido_desconhecido"
    if n.provider_ref and pg.provider_ref and n.provider_ref != pg.provider_ref:
        return "referencia_divergente"
    if n.provider_payment_id and not pg.provider_payment_id:
        pg.provider_payment_id = n.provider_payment_id
    if n.status == "aprovado":
        if n.valor_centavos != pg.valor_centavos or (n.moeda or "BRL").upper() != pg.moeda:
            audit.registrar("pagamento_valor_divergente", pg.usuario_id, f"pg={pg.id} recebido={n.valor_centavos} {n.moeda}", "alerta")
            if pg.status in ("criado", "pendente"):  # sai da fila de reconciliação; só um administrador resolve
                pg.status, pg.observacao = "divergente", f"valor recebido {n.valor_centavos} {n.moeda} difere do pedido ({pg.valor_centavos} {pg.moeda})"
            return "valor_divergente"  # nunca libera produto por valor diferente do pedido
        dono = db.session.get(Usuario, pg.usuario_id)
        if dono is None or (dono.email or "").endswith("@exquest.invalid"):  # conta excluída: não entrega nada, fica para reembolso manual
            if pg.status in ("criado", "pendente"):
                pg.status, pg.observacao = "divergente", "conta excluída antes da aprovação: reembolsar no provedor"
            audit.registrar("pagamento_conta_excluida", pg.usuario_id, f"pg={pg.id}", "alerta")
            return "conta_excluida"
        r = db.session.execute(update(Pagamento).where(Pagamento.id == pg.id, Pagamento.status.in_(("criado", "pendente", "recusado", "expirado", "divergente")))
                               .values(status="aprovado", aprovado_em=clock.agora(), atualizado_em=clock.agora()))
        if r.rowcount != 1:
            return "ja_processado"
        db.session.refresh(pg)
        _entregar(pg)
        return "aprovado"
    if n.status in ("reembolsado", "contestado"):
        r = db.session.execute(update(Pagamento).where(Pagamento.id == pg.id, Pagamento.status == "aprovado")
                               .values(status=n.status, reembolsado_em=clock.agora(), atualizado_em=clock.agora()))
        if r.rowcount != 1:
            return "ja_processado"
        db.session.refresh(pg)
        _estornar(pg)
        return n.status
    if n.status in ("recusado", "cancelado", "expirado") and pg.status in ("criado", "pendente"):
        pg.status = n.status
        return n.status
    return "ignorado"


def processar_webhook(provider: str, n: Notificacao | None, tipo_bruto: str = "") -> str:
    """Dedupe por (provedor, evento) + aplicação. O chamador faz commit."""
    if n is None:
        return "ignorado"
    ev = EventoWebhook(provider=provider, evento_id=n.evento_id[:200], tipo=(tipo_bruto or n.tipo)[:80])
    try:
        with db.session.begin_nested():
            db.session.add(ev)
    except IntegrityError:  # índice único: já visto (qualquer outro erro sobe e o provedor tenta de novo)
        return "duplicado"
    ev.resultado = aplicar(n, provider)
    ev.processado_em = clock.agora()
    return ev.resultado


def reconciliar(pg: Pagamento) -> str:
    if pg.status not in ("criado", "pendente"):
        return pg.status
    n = PROVEDORES[pg.provider].reconciliar(pg)
    if n is None:
        return pg.status
    n.pagamento_id = pg.id  # a consulta foi feita pelo NOSSO pedido
    res = aplicar(n, pg.provider)
    return res
