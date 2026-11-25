# Pendências que dependem do responsável

1. **Rotacionar credenciais** que estavam no `.env` original: MAIL_PASSWORD, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY, MP_ACCESS_TOKEN, SECRET_KEY. Considere-as comprometidas.
2. **Textos legais**: `termos.html` e `privacidade.html` foram escritos a partir do que o sistema realmente faz (dados coletados, cookies, pagamentos, exclusão e exportação), mas **não passaram por advogado**. Revise (principalmente reembolso/arrependimento, menores de idade, base legal, nome e contato do controlador e do encarregado LGPD) e defina `CONTATO_EMAIL`, que é exibido neles. Os reembolsos hoje são processados manualmente no painel do Mercado Pago/Stripe.
3. **Credenciais dos serviços** e teste ponta a ponta de Mercado Pago, Stripe, SMTP e Google (ver o tutorial).
4. **Docker**: rodar `docker compose up --build` em um host com Docker antes do deploy.
5. **Agendamento** dos comandos periódicos (guia, seção 4).
6. **Domínio, HTTPS e proxy** (`deploy/nginx.conf`) e `TRUSTED_PROXIES`.
7. **Valores da economia** (recompensas de missões e competições, preços) foram definidos por estimativa; ajuste conforme o uso real.
8. **Correção por IA** de questões discursivas não está integrada: a correção é local (similaridade de texto). Se quiser um modelo de linguagem, é uma nova integração a ser feita em `grading.avaliar_discursiva`.

## Infraestrutura de desempenho (2026-11-18)

- Rodar `docker compose up --build` (e `--scale web=2`) num host com Docker: o arquivo foi validado com `docker compose config`, mas as imagens não foram construídas aqui.
- Contratar/configurar um CDN (opcional) e definir `CDN_URL`; contratar Redis gerenciado (opcional) e definir `REDIS_URL` e `RATELIMIT_STORAGE_URI`.
- Para mais de um servidor: PostgreSQL na mesma região do app, uploads em volume compartilhado.
- Para OpenTelemetry: um coletor OTLP (Grafana, Honeycomb etc.) e `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Medir em celulares reais e redes lentas depois do deploy; as métricas de usuários reais aparecem em `/admin/desempenho`.
