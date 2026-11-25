"""Mercado Pago Checkout Pro (pagamento único). Docs: developers/docs/checkout-pro e /notifications/webhooks.
Segurança: a assinatura do webhook é validada (HMAC-SHA256 do manifest) E o pagamento é sempre reconsultado na API
com o nosso token antes de liberar qualquer coisa; o corpo do webhook nunca é a fonte da verdade."""
import hashlib
import hmac
from decimal import Decimal

import requests
from flask import current_app

from app.providers import http

from app.providers.base import AssinaturaInvalida, Notificacao, ProviderIndisponivel

API = "https://api.mercadopago.com"
STATUS = {"approved": "aprovado", "authorized": "aprovado", "pending": "pendente", "in_process": "pendente", "in_mediation": "contestado",
          "rejected": "recusado", "cancelled": "cancelado", "refunded": "reembolsado", "charged_back": "contestado"}


def disponivel() -> bool:
    return bool(current_app.config.get("MP_ACCESS_TOKEN"))


def _h():
    t = current_app.config.get("MP_ACCESS_TOKEN")
    if not t:
        raise ProviderIndisponivel("Mercado Pago não está configurado neste ambiente.")
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def criar_checkout(pg, email: str) -> tuple[str, str]:
    base = current_app.config["BASE_URL"]
    corpo = {"items": [{"id": pg.produto_ref, "title": pg.descricao[:120], "quantity": 1, "currency_id": "BRL",
                        "unit_price": float(Decimal(pg.valor_centavos) / 100)}],
             "external_reference": str(pg.id), "payer": {"email": email},
             "notification_url": f"{base}/webhooks/mercadopago",
             "back_urls": {k: f"{base}/pagamentos/retorno/{pg.id}" for k in ("success", "failure", "pending")}}
    if base.startswith("https://"):  # auto_return exige URL pública https
        corpo["auto_return"] = "approved"
    try:
        r = requests.post(f"{API}/checkout/preferences", json=corpo, headers=_h(), timeout=http.timeout())
        r.raise_for_status()
        d = r.json()
    except requests.RequestException:
        raise ProviderIndisponivel("Não foi possível falar com o Mercado Pago agora. Tente novamente em instantes.")
    url = d["init_point"] if not current_app.config.get("MP_SANDBOX") else d.get("sandbox_init_point", d["init_point"])
    return str(d["id"]), url


def validar_assinatura(headers, args) -> None:
    segredo = current_app.config.get("MP_WEBHOOK_SECRET")
    if not segredo:
        raise AssinaturaInvalida("MP_WEBHOOK_SECRET ausente")
    partes = dict(p.strip().split("=", 1) for p in (headers.get("x-signature") or "").split(",") if "=" in p)
    ts, v1 = partes.get("ts"), partes.get("v1")
    if not ts or not v1:
        raise AssinaturaInvalida("cabeçalho x-signature ausente")
    manifest = ""
    if args.get("data.id"):
        manifest += f"id:{args['data.id'].lower()};"
    if headers.get("x-request-id"):
        manifest += f"request-id:{headers['x-request-id']};"
    manifest += f"ts:{ts};"
    esperado = hmac.new(segredo.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado.encode(), v1.encode("utf-8", "replace")):
        raise AssinaturaInvalida("assinatura não confere")


def _notif(p: dict, evento_id: str) -> Notificacao:
    return Notificacao(evento_id=evento_id, tipo="payment", pagamento_id=p.get("external_reference"), status=STATUS.get(p.get("status"), "pendente"),
                       provider_payment_id=str(p["id"]), valor_centavos=int(Decimal(str(p.get("transaction_amount", 0))) * 100),
                       moeda=p.get("currency_id"))


def consultar_pagamento(payment_id: str) -> Notificacao:
    try:
        r = requests.get(f"{API}/v1/payments/{payment_id}", headers=_h(), timeout=http.timeout())
        r.raise_for_status()
        return _notif(r.json(), f"payment:{payment_id}")
    except requests.RequestException:
        raise ProviderIndisponivel("Falha ao consultar o Mercado Pago.")


def interpretar_webhook(headers, args, corpo: dict) -> Notificacao | None:
    validar_assinatura(headers, args)
    if (args.get("type") or corpo.get("type")) != "payment":
        return None  # tópicos que não usamos (merchant_order etc.) são só confirmados
    pid = args.get("data.id") or (corpo.get("data") or {}).get("id")
    if not pid or not str(pid).isascii() or not str(pid).isdigit():  # id vira parte da URL da API: só dígitos
        return None
    n = consultar_pagamento(str(pid))
    n.evento_id = f"payment:{pid}:{n.status}"
    return n


def reconciliar(pg) -> Notificacao | None:
    """Consulta ativa (volta do checkout / webhook atrasado): acha o pagamento pelo nosso external_reference."""
    try:
        r = requests.get(f"{API}/v1/payments/search", params={"external_reference": str(pg.id), "sort": "date_created", "criteria": "desc"},
                         headers=_h(), timeout=http.timeout())
        r.raise_for_status()
        itens = r.json().get("results") or []
    except requests.RequestException:
        raise ProviderIndisponivel("Falha ao consultar o Mercado Pago.")
    return _notif(itens[0], f"payment:{itens[0]['id']}:reconciliar") if itens else None
