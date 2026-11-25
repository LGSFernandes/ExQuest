import hashlib
import hmac
import json
import time

import pytest

from app.extensions import db
from app.models import EventoWebhook, Pagamento, Usuario
from app.providers import mercadopago, stripe_provider
from app.providers.base import AssinaturaInvalida
from app.services import pagamentos as svc
from app.services import wallet
from tests.test_auth import registrar

SEG_STRIPE, SEG_MP = "whsec_teste", "mp_segredo_teste"


@pytest.fixture
def pg_app(app):
    app.config.update(STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET=SEG_STRIPE, MP_ACCESS_TOKEN="APP_USR-x", MP_WEBHOOK_SECRET=SEG_MP,
                      BASE_URL="http://localhost")
    return app


def _pedido(client, tipo="moedas", produto="starter", prov="stripe"):
    registrar(client)
    u = Usuario.query.filter_by(email="ana@exemplo.com").one()
    pg = Pagamento(usuario_id=u.id, tipo=tipo, produto_ref=produto, provider=prov, status="pendente", chave_idempotencia=f"k{time.time_ns()}",
                   descricao="teste", provider_ref="cs_1")
    if tipo == "moedas":
        pg.valor_centavos, pg.moedas_total = 1190, 200  # base do pacote; o bônus de 1ª compra entra na entrega
    else:
        pg.plano, pg.ciclo = produto.split(":"); pg.valor_centavos = 1990
    db.session.add(pg); db.session.commit()
    return u, pg


def _stripe_post(client, evento, segredo=SEG_STRIPE, t=None):
    corpo = json.dumps(evento).encode()
    t = int(t or time.time())
    sig = hmac.new(segredo.encode(), f"{t}.".encode() + corpo, hashlib.sha256).hexdigest()
    return client.post("/webhooks/stripe", data=corpo, headers={"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"})


def _evento(pg, eid="evt_1", valor=None, tipo="checkout.session.completed", pago="paid"):
    return {"id": eid, "type": tipo, "data": {"object": {"id": "cs_1", "client_reference_id": str(pg.id), "payment_status": pago,
            "amount_total": valor or pg.valor_centavos, "currency": "brl", "payment_intent": "pi_1"}}}


def test_stripe_assinatura_invalida_ou_velha_ou_sem_segredo_nao_processa(client, pg_app):
    u, pg = _pedido(client)
    assert _stripe_post(client, _evento(pg), segredo="outro").status_code == 400
    assert _stripe_post(client, _evento(pg), t=time.time() - 3600).status_code == 400
    assert client.post("/webhooks/stripe", data=b"{}").status_code == 400
    pg_app.config["STRIPE_WEBHOOK_SECRET"] = ""
    assert _stripe_post(client, _evento(pg)).status_code == 400
    db.session.refresh(pg)
    assert pg.status == "pendente" and Usuario.query.get(u.id).moedas == 0


def test_stripe_pagamento_credita_uma_vez_mesmo_com_reenvio_e_eventos_diferentes(client, pg_app):
    u, pg = _pedido(client)
    assert _stripe_post(client, _evento(pg)).status_code == 200
    assert _stripe_post(client, _evento(pg)).get_json()["resultado"] == "duplicado"
    assert _stripe_post(client, _evento(pg, eid="evt_2", tipo="checkout.session.async_payment_succeeded")).get_json()["resultado"] == "ja_processado"
    db.session.refresh(u); db.session.refresh(pg)
    assert u.moedas == 220 and pg.status == "aprovado" and pg.provider_payment_id == "pi_1"
    assert wallet.conferir(u.id)[0] and EventoWebhook.query.count() == 2
    from app.models import Notificacao as N
    assert [n.titulo for n in N.query.filter_by(usuario_id=u.id)] == ["Pagamento confirmado"]  # uma só, apesar do reenvio


def test_valor_divergente_nao_libera_e_pedido_alheio_e_ignorado(client, pg_app):
    u, pg = _pedido(client)
    assert _stripe_post(client, _evento(pg, valor=100)).get_json()["resultado"] == "valor_divergente"
    assert _stripe_post(client, {"id": "e9", "type": "checkout.session.completed", "data": {"object": {"client_reference_id": "99999", "payment_status": "paid", "amount_total": 1190, "currency": "brl"}}}).get_json()["resultado"] == "pedido_desconhecido"
    db.session.refresh(u); db.session.refresh(pg)
    assert u.moedas == 0 and pg.status == "divergente"


def test_pagamento_pendente_pix_so_libera_quando_pago_e_reembolso_estorna(client, pg_app):
    u, pg = _pedido(client)
    _stripe_post(client, _evento(pg, pago="unpaid"))
    db.session.refresh(pg); assert pg.status == "pendente" and Usuario.query.get(u.id).moedas == 0
    _stripe_post(client, _evento(pg, eid="evt_p", tipo="checkout.session.async_payment_succeeded"))
    assert Usuario.query.get(u.id).moedas == 220
    r = _stripe_post(client, {"id": "evt_r", "type": "charge.refunded", "data": {"object": {"payment_intent": "pi_1"}}})
    assert r.get_json()["resultado"] == "reembolsado"
    db.session.refresh(u); db.session.refresh(pg)
    assert u.moedas == 0 and pg.status == "reembolsado" and wallet.conferir(u.id)[0]
    from app.models import Notificacao as N
    assert {n.titulo for n in N.query.filter_by(usuario_id=u.id)} == {"Pagamento confirmado", "Pagamento estornado"}


def test_estorno_parcial_quando_moedas_ja_foram_gastas(client, pg_app):
    u, pg = _pedido(client)
    _stripe_post(client, _evento(pg))
    wallet.debitar(u.id, 200, "compra_loja", "gasto:1"); db.session.commit()
    _stripe_post(client, {"id": "evt_r", "type": "charge.refunded", "data": {"object": {"payment_intent": "pi_1"}}})
    db.session.refresh(u); db.session.refresh(pg)
    assert u.moedas == 0 and "parcial" in pg.observacao and wallet.conferir(u.id)[0]


def test_premium_ativa_renova_soma_dias_e_upgrade_substitui(client, pg_app):
    from datetime import timedelta
    from app import clock
    u, pg = _pedido(client, "premium", "basic:mensal")
    _stripe_post(client, _evento(pg))
    db.session.refresh(u)
    assert u.plano_premium == "basic" and u.premium_ativo
    fim1 = u.premium_expira
    pg2 = Pagamento(usuario_id=u.id, tipo="premium", produto_ref="basic:mensal", provider="stripe", status="pendente", valor_centavos=1990,
                    plano="basic", ciclo="mensal", chave_idempotencia="k-r", provider_ref="cs_1"); db.session.add(pg2); db.session.commit()
    _stripe_post(client, _evento(pg2, eid="evt_r2"))
    db.session.refresh(u)
    assert u.premium_expira - fim1 == timedelta(days=30)  # renovação soma ao fim atual
    pg3 = Pagamento(usuario_id=u.id, tipo="premium", produto_ref="advan:mensal", provider="stripe", status="pendente", valor_centavos=1990,
                    plano="advan", ciclo="mensal", chave_idempotencia="k-u", provider_ref="cs_1"); db.session.add(pg3); db.session.commit()
    _stripe_post(client, _evento(pg3, eid="evt_u"))
    db.session.refresh(u)
    assert u.plano_premium == "advan" and u.premium_expira - clock.agora() <= timedelta(days=30, minutes=1)
    with pytest.raises(ValueError):
        from app.services import premium
        premium.validar_compra(u, "basic", "mensal")  # downgrade enquanto superior ativo


def test_mercadopago_assinatura_manifest_e_fluxo_com_consulta_a_api(client, pg_app, monkeypatch):
    u, pg = _pedido(client, prov="mercadopago")
    def assinar(data_id, req_id, ts, seg=SEG_MP):
        m = f"id:{data_id.lower()};request-id:{req_id};ts:{ts};"
        return {"x-signature": f"ts={ts},v1={hmac.new(seg.encode(), m.encode(), hashlib.sha256).hexdigest()}", "x-request-id": req_id}
    pay = {"id": 555, "status": "approved", "external_reference": str(pg.id), "transaction_amount": 11.9, "currency_id": "BRL"}
    class R:
        def raise_for_status(self): pass
        def json(self): return pay
    monkeypatch.setattr(mercadopago.requests, "get", lambda *a, **k: R())
    url = "/webhooks/mercadopago?data.id=555&type=payment"
    assert client.post(url, json={}, headers=assinar("555", "r1", 1, seg="errado")).status_code == 400
    assert client.post(url, json={}).status_code == 400
    ok = client.post(url, json={"type": "payment", "data": {"id": "555"}}, headers=assinar("555", "r1", 1))
    assert ok.status_code == 200 and ok.get_json()["resultado"] == "aprovado"
    assert client.post(url, json={}, headers=assinar("555", "r1", 1)).get_json()["resultado"] == "duplicado"
    db.session.refresh(u); assert u.moedas == 220
    # a consulta à API é a fonte da verdade: valor menor na API não libera
    u2, pg2 = pg.usuario_id, Pagamento(usuario_id=pg.usuario_id, tipo="moedas", produto_ref="starter", provider="mercadopago", status="pendente",
        valor_centavos=1190, moedas_total=200, chave_idempotencia="k2"); db.session.add(pg2); db.session.commit()
    pay.update(id=556, external_reference=str(pg2.id), transaction_amount=1.0)
    r = client.post("/webhooks/mercadopago?data.id=556&type=payment", json={}, headers=assinar("556", "r2", 2))
    assert r.get_json()["resultado"] == "valor_divergente"


def test_checkout_cria_pedido_so_com_provedor_configurado_e_nunca_confia_no_preco_do_cliente(client, pg_app, monkeypatch):
    registrar(client)
    class R:
        def raise_for_status(self): pass
        def json(self): return {"id": "cs_9", "url": "https://checkout.stripe.com/c/pay/cs_9"}
    visto = {}
    def post(url, data=None, **k): visto.update(data); return R()
    monkeypatch.setattr(stripe_provider.requests, "post", post)
    r = client.post("/pagamentos/checkout", data={"tipo": "moedas", "produto": "popular", "provider": "stripe", "preco": "1"})
    assert r.status_code == 302 and r.headers["Location"].startswith("https://checkout.stripe.com/")
    assert visto["line_items[0][price_data][unit_amount]"] == "2490" and visto["mode"] == "payment"
    pg = Pagamento.query.one()
    assert pg.status == "pendente" and pg.moedas_total == 400 + 50  # o bônus de 1ª compra só é somado na entrega
    pg_app.config["STRIPE_SECRET_KEY"] = ""
    r = client.post("/pagamentos/checkout", data={"tipo": "moedas", "produto": "popular", "provider": "stripe"}, follow_redirects=True)
    assert b"n\xc3\xa3o est\xc3\xa1 dispon" in r.data
    assert client.post("/pagamentos/checkout", data={"tipo": "moedas", "produto": "inexistente", "provider": "stripe"}).status_code == 302


def test_retorno_do_navegador_nao_libera_e_e_privado(client, pg_app):
    u, pg = _pedido(client)
    html = client.get(f"/pagamentos/retorno/{pg.id}?status=approved").data.decode()
    assert "Aguardando confirma" in html and 'http-equiv="refresh"' in html
    db.session.refresh(u); assert u.moedas == 0
    client.post("/sair"); registrar(client, username="bia", email="bia@exemplo.com")
    assert client.get(f"/pagamentos/retorno/{pg.id}").status_code == 404


def test_paginas_de_pagamento_renderizam_sem_provedor(client, app):
    registrar(client)
    for url in ("/loja/moedas", "/premium", "/premium/assinaturas"):
        r = client.get(url); assert r.status_code == 200 and b"style=" not in r.data, url
    assert b"ainda n" in client.get("/premium").data


def test_comandos_de_manutencao(app):
    r = app.test_cli_runner()
    assert "0 conta" in r.invoke(args=["premium-expirar"]).output
    assert "0 pedido" in r.invoke(args=["pagamentos-reconciliar"]).output


def test_bonus_de_primeira_compra_so_vale_para_um_de_dois_checkouts_abertos(client, pg_app):
    u, a = _pedido(client)
    b = Pagamento(usuario_id=u.id, tipo="moedas", produto_ref="starter", provider="stripe", status="pendente", valor_centavos=1190,
                  moedas_total=200, chave_idempotencia="kb", descricao="teste", provider_ref="cs_2"); db.session.add(b); db.session.commit()
    from app.services import pagamentos
    pagamentos._entregar(a); a.status = "aprovado"; db.session.commit()
    pagamentos._entregar(b); b.status = "aprovado"; db.session.commit()
    assert (a.moedas_total, b.moedas_total) == (220, 200) and Usuario.query.get(u.id).moedas == 420
