"""Stripe Checkout (pagamento único) via API REST. Webhook: HMAC-SHA256 de "{t}.{corpo bruto}" com tolerância de 5 min."""
import hashlib
import hmac
import time

import requests
from flask import current_app

from app.providers import http
from app.providers.base import AssinaturaInvalida, Notificacao, ProviderIndisponivel

API = "https://api.stripe.com/v1"
TOLERANCIA_S = 300


def disponivel() -> bool:
    return bool(current_app.config.get("STRIPE_SECRET_KEY"))


def _auth():
    k = current_app.config.get("STRIPE_SECRET_KEY")
    if not k:
        raise ProviderIndisponivel("Stripe não está configurado neste ambiente.")
    return {"Authorization": f"Bearer {k}"}


def criar_checkout(pg, email: str) -> tuple[str, str]:
    base = current_app.config["BASE_URL"]
    form = {"mode": "payment", "client_reference_id": str(pg.id), "customer_email": email,
            "metadata[pagamento_id]": str(pg.id), "payment_intent_data[metadata][pagamento_id]": str(pg.id),
            "line_items[0][quantity]": "1", "line_items[0][price_data][currency]": "brl",
            "line_items[0][price_data][unit_amount]": str(pg.valor_centavos),
            "line_items[0][price_data][product_data][name]": pg.descricao[:120],
            "success_url": f"{base}/pagamentos/retorno/{pg.id}", "cancel_url": f"{base}/pagamentos/retorno/{pg.id}"}
    try:
        r = requests.post(f"{API}/checkout/sessions", data=form, headers={**_auth(), "Idempotency-Key": pg.chave_idempotencia[:60]}, timeout=http.timeout())
        r.raise_for_status()
        d = r.json()
    except requests.RequestException:
        raise ProviderIndisponivel("Não foi possível falar com o Stripe agora. Tente novamente em instantes.")
    return d["id"], d["url"]


def validar_assinatura(cabecalho: str, corpo_bruto: bytes, agora: float | None = None) -> None:
    segredo = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    if not segredo:
        raise AssinaturaInvalida("STRIPE_WEBHOOK_SECRET ausente")
    itens = [p.split("=", 1) for p in (cabecalho or "").split(",") if "=" in p]
    t = next((v for k, v in itens if k == "t"), None)
    assinaturas = [v for k, v in itens if k == "v1"]  # pode haver várias durante a troca de segredo
    if not t or not (t.isascii() and t.isdigit()) or not assinaturas:
        raise AssinaturaInvalida("cabeçalho Stripe-Signature inválido")
    if abs((agora or time.time()) - int(t)) > TOLERANCIA_S:
        raise AssinaturaInvalida("timestamp fora da tolerância")
    esperado = hmac.new(segredo.encode(), f"{t}.".encode() + corpo_bruto, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(esperado.encode(), s.encode("utf-8", "replace")) for s in assinaturas):
        raise AssinaturaInvalida("assinatura não confere")


def _da_sessao(s: dict, evento_id: str, status: str) -> Notificacao:
    return Notificacao(evento_id=evento_id, tipo="checkout", pagamento_id=s.get("client_reference_id") or (s.get("metadata") or {}).get("pagamento_id"),
                       status=status, provider_payment_id=s.get("payment_intent"), valor_centavos=s.get("amount_total"),
                       moeda=(s.get("currency") or "").upper(), provider_ref=s.get("id"))


def interpretar_webhook(evento: dict) -> Notificacao | None:
    tipo, obj = evento.get("type"), (evento.get("data") or {}).get("object") or {}
    eid = evento.get("id", "")
    if tipo in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        pago = obj.get("payment_status") == "paid"
        return _da_sessao(obj, eid, "aprovado" if pago else "pendente")
    if tipo == "checkout.session.async_payment_failed":
        return _da_sessao(obj, eid, "recusado")
    if tipo == "checkout.session.expired":
        return _da_sessao(obj, eid, "expirado")
    if tipo in ("charge.refunded", "charge.dispute.created"):
        return Notificacao(evento_id=eid, tipo="charge", status="reembolsado" if tipo == "charge.refunded" else "contestado",
                           provider_payment_id=obj.get("payment_intent"), pagamento_id=(obj.get("metadata") or {}).get("pagamento_id"))
    return None


def reconciliar(pg) -> Notificacao | None:
    if not pg.provider_ref:
        return None
    try:
        r = requests.get(f"{API}/checkout/sessions/{pg.provider_ref}", headers=_auth(), timeout=http.timeout())
        r.raise_for_status()
        s = r.json()
    except requests.RequestException:
        raise ProviderIndisponivel("Falha ao consultar o Stripe.")
    st = "aprovado" if s.get("payment_status") == "paid" else "expirado" if s.get("status") == "expired" else "pendente"
    return _da_sessao(s, f"sessao:{s['id']}:reconciliar", st)
