"""Entrada dos webhooks. Sem CSRF (quem chama é o provedor), mas SÓ processa com assinatura válida.
200 = recebido/ignorado; 400 = assinatura inválida; 500 = falha nossa (o provedor tenta de novo)."""
import json

from flask import Blueprint, current_app, request

from app.extensions import csrf, db, limiter
from app.providers import mercadopago, stripe_provider
from app.providers.base import AssinaturaInvalida, ProviderIndisponivel
from app.services import audit, pagamentos

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


def _resposta(provider, interpretar):
    try:
        n = interpretar()
        res = pagamentos.processar_webhook(provider, n)
        db.session.commit()
        return {"ok": True, "resultado": res}, 200
    except AssinaturaInvalida as e:
        db.session.rollback()
        audit.registrar("webhook_assinatura_invalida", None, f"{provider}: {e}", "alerta", request=request)
        db.session.commit()
        return {"ok": False}, 400
    except (ProviderIndisponivel, Exception) as e:  # noqa: BLE001
        db.session.rollback()
        current_app.logger.exception("falha no webhook %s: %s", provider, e)
        return {"ok": False}, 500


@bp.post("/mercadopago")
@csrf.exempt
@limiter.limit("300 per minute")  # barra enchente anônima (cada assinatura inválida grava uma linha de auditoria)
def mercadopago_hook():
    corpo = request.get_json(silent=True) or {}
    return _resposta("mercadopago", lambda: mercadopago.interpretar_webhook(request.headers, request.args, corpo))


@bp.post("/stripe")
@csrf.exempt
@limiter.limit("300 per minute")
def stripe_hook():
    bruto = request.get_data()  # corpo BRUTO: a assinatura cobre os bytes exatos

    def interpretar():
        stripe_provider.validar_assinatura(request.headers.get("Stripe-Signature", ""), bruto)
        try:
            return stripe_provider.interpretar_webhook(json.loads(bruto))
        except ValueError:
            return None
    return _resposta("stripe", interpretar)
