# Segurança do ExQuest

Estado: auditoria focada (F9b, parcial). A auditoria completa em seis fases será repetida ao final da F10.

## Achados e correções até agora
| # | Achado | Ação |
|---|--------|------|
| 1 | Dependências com vulnerabilidades conhecidas (Flask, Werkzeug, Authlib, cryptography, requests, urllib3, etc.) | Atualizadas; `pip-audit` limpo. Backup do arquivo antigo fora do projeto. |
| 2 | Blocos Jinja dentro de `{% include %}` não aceitam sobrescrita: títulos e `noindex` não eram aplicados | Criado `_layout.html`; teste de regressão. |
| 3 | Fixture de teste de CSRF devolvia o token como resposta (hook `before_request` retornando valor) | Corrigido no teste; não afeta produção. |

## Cobertura por testes automatizados (`tests/test_seguranca_web.py`)
- Nenhuma rota privada acessível sem login.
- CSRF exigido em todo POST, inclusive JSON; webhooks só pela assinatura.
- XSS (escape), entradas estilo injeção de SQL, path traversal, mass assignment.
- Uploads poliglota rejeitados; cookies com flags seguras; cabeçalhos de segurança; erros 500 sem detalhes.
- Economia: concorrência real com threads (débito atômico, idempotência).
- Webhooks: assinatura HMAC, tolerância de tempo, deduplicação, valor/moeda conferidos.

## Não verificado
- Integração real com Mercado Pago, Stripe, SMTP e Google (sem credenciais).
- Varredura completa nas seis fases da skill security-audit (pendente, final da F10).

## Ação do responsável
Rotacione as credenciais que estavam no `.env` original: MAIL_PASSWORD, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY, MP_ACCESS_TOKEN e SECRET_KEY.
