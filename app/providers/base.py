class ProviderIndisponivel(Exception):
    """Credenciais ausentes ou provedor fora do ar. A mensagem é segura para o usuário."""


class AssinaturaInvalida(Exception):
    """Webhook sem assinatura válida: nunca processar."""


class Notificacao:
    """Resultado normalizado de um webhook ou consulta. `pagamento_id` é o nosso id (external_reference)."""

    def __init__(self, *, evento_id, tipo, pagamento_id=None, status=None, provider_payment_id=None, valor_centavos=None,
                 moeda=None, provider_ref=None):
        self.evento_id, self.tipo, self.pagamento_id, self.status = evento_id, tipo, pagamento_id, status
        self.provider_payment_id, self.valor_centavos, self.moeda, self.provider_ref = provider_payment_id, valor_centavos, moeda, provider_ref
