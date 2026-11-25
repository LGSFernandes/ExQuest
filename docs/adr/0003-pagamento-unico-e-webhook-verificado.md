# ADR 0003: pagamentos únicos, webhook verificado e reconsulta

**Status:** aceita

**Contexto:** Mercado Pago e Stripe. Webhooks podem ser forjados, duplicados ou perdidos.

**Decisão:** Premium pré-pago (sem recorrência) e pacotes de moedas. O webhook só é aceito com assinatura válida; o pagamento é sempre reconsultado na API do provedor, e valor e moeda são conferidos. `pagamentos-reconciliar` cobre webhooks perdidos.

**Consequências:** sem renovação automática (o aluno recompra). Cartões nunca passam pelo ExQuest. Exige URL pública para os webhooks.
