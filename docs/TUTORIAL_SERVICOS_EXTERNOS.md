# Tutorial de serviços externos

Todos são opcionais: sem a configuração, o recurso aparece como indisponível. Nenhuma integração foi exercitada contra o serviço real durante o desenvolvimento (só com testes locais de assinatura e respostas simuladas); faça o teste ponta a ponta de cada uma antes de abrir ao público.

## E-mail (recuperação de senha)

1. Use um provedor SMTP (por exemplo o da sua hospedagem, ou um serviço transacional).
2. Preencha `MAIL_SERVER`, `MAIL_PORT` (587 com `MAIL_USE_TLS=true`, ou 465 com `MAIL_USE_SSL=true`), `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`.
3. Gmail exige senha de app (verificação em duas etapas ativa).
4. Teste: peça recuperação de senha para uma conta sua e confira a chegada e o link (usa `BASE_URL`).

## Login com Google

1. Google Cloud Console, projeto, "APIs e serviços", "Credenciais", "ID do cliente OAuth" (aplicativo da Web).
2. URI de redirecionamento autorizado: `https://SEU-DOMINIO/entrar/google/retorno` (em dev: `http://127.0.0.1:5000/entrar/google/retorno`).
3. Preencha `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`. O botão só aparece com os dois definidos. Só contas com e-mail verificado entram.

## Mercado Pago (Checkout Pro, pagamento único)

Conferido contra a documentação oficial de webhooks do Mercado Pago (formato do `x-signature` e do manifest `id:...;request-id:...;ts:...;` com HMAC-SHA256). A conta e a chamada reais não foram testadas.

1. Painel de desenvolvedores, "Suas integrações", crie a aplicação e copie o Access Token para `MP_ACCESS_TOKEN` (use as credenciais de teste primeiro, com `MP_SANDBOX=true`).
2. Na aplicação, abra "Webhooks", informe a URL `https://SEU-DOMINIO/webhooks/mercadopago`, marque o evento "Pagamentos" (payment) e salve. Só depois de salvar o painel gera a "assinatura secreta": copie-a para `MP_WEBHOOK_SECRET`. Sem ela todo webhook é recusado.
3. O ExQuest também envia `notification_url` em cada pagamento, então as notificações chegam mesmo se o painel não for configurado, mas a chave secreta continua vindo do painel.
4. O site precisa de URL pública HTTPS (em dev, use um túnel). `auto_return` só é enviado com `BASE_URL` https.
5. O sistema sempre reconsulta o pagamento na API do Mercado Pago antes de liberar qualquer coisa; se um webhook falhar, `flask --app main manutencao` (ou `pagamentos-reconciliar`) resolve.

## Stripe (Checkout, pagamento único)

1. Dashboard, "Desenvolvedores", "Chaves de API": `STRIPE_SECRET_KEY` (chave de teste primeiro).
2. "Webhooks", endpoint `https://SEU-DOMINIO/webhooks/stripe`, com exatamente estes eventos (os que o código trata): `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`, `charge.refunded` e `charge.dispute.created`. Copie o "signing secret" (`whsec_...`) para `STRIPE_WEBHOOK_SECRET`.
3. Teste local: `stripe listen --forward-to localhost:5000/webhooks/stripe` (a CLI mostra o `whsec_` temporário).
4. A assinatura é validada com tolerância de 5 minutos. Não há cobrança recorrente: o Premium é pré-pago e expira.
