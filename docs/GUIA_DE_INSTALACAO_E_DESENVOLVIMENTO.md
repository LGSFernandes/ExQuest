# Guia de instalação e desenvolvimento

## 1. Estrutura

- `app/blueprints/`: rotas finas (auth, questoes, simulados, revisao, colecoes, missoes, competicoes, ranking, loja, perfil, social/chat, notificacoes, pagamentos, webhooks, admin).
- `app/services/`: regras de negócio (grading, xp, wallet/ledger, plans, premium, pagamentos, colecoes, missoes, competicoes, amizades, chat, uploads, backup...).
- `app/models/`: modelos em pacote. `app/providers/`: Mercado Pago e Stripe. `app/templates`, `app/static` (CSS em camadas, JS sem inline).
- `migrations/`: Alembic. `deploy/nginx.conf`: exemplo de proxy. `tests/`: pytest.

## 2. Regras que o código impõe

- Economia: todo crédito/débito de moedas passa por `wallet` (ledger com chave de idempotência). XP só na primeira resposta correta de cada questão.
- Cada plano define limites e recursos em `app/services/plans.py` (`usuario.limite(...)`, `usuario.pode(...)`).
- CSP estrita: nada de `style=`, `onclick=` ou `<script>` inline. Valores dinâmicos de estilo vão em `data-vars="--var:valor"`.
- Datas no banco em UTC sem fuso; exibição e "dia" em America/Sao_Paulo (`app/clock.py`).

## 3. Banco de dados

- Padrão: SQLite em `instance/database.db` (WAL, chaves estrangeiras ligadas). Para PostgreSQL: `pip install -r requirements-postgres.txt` e `DATABASE_URL=postgresql+psycopg://...`.
- Alterou modelo? `flask --app main db migrate -m "descrição"`, revise o arquivo gerado e aplique com `flask --app main migrar`.
- `migrar` faz backup antes (SQLite) e verifica integridade depois. Em PostgreSQL faça `pg_dump` antes.
- Backup manual: `flask --app main backup` (gera em `instance/backups/`).

## 4. Comandos

| Comando | Uso |
|---|---|
| `migrar` | backup, migrations e verificação |
| `loja-seed` | cria itens do catálogo que faltam |
| `promover-admin EMAIL` | torna uma conta administradora |
| `manutencao` | rotina única (a que deve ser agendada): competições, Premium e pagamentos |
| `premium-expirar` | encerra assinaturas vencidas |
| `pagamentos-reconciliar --minutos N` | consulta o provedor para pedidos pendentes |
| `competicoes-encerrar` | encerra competições vencidas e paga prêmios |
| `backup` | backup do SQLite |

Agende `flask --app main manutencao` a cada 5 minutos (cron, systemd timer). No Docker Compose isso já está pronto: o serviço `tarefas` roda a rotina em laço. Além disso, o próprio app executa uma versão leve (competições e Premium) no máximo 1x por minuto por processo quando recebe qualquer requisição, mas só o agendamento cobre os períodos sem visitas. Tudo é idempotente: rodar em dobro não paga duas vezes.

## 5. Produção

1. `APP_ENV=production`, `SECRET_KEY` forte (obrigatória), `BASE_URL=https://seu-dominio`, `TRUSTED_PROXIES` igual ao número de proxies na frente.
2. HTTPS obrigatório (cookies `Secure`). Use `deploy/nginx.conf` como base e não duplique o cabeçalho CSP no proxy.
3. Vários workers ou instâncias exigem `RATELIMIT_STORAGE_URI=redis://...`; com memória, cada worker conta separado.
4. Uploads ficam em `app/static/data/` (públicos) e `instance/private/` (chat). Faça backup dos dois junto com o banco.

### Docker

```bash
docker compose up -d --build                  # 1 instância web (SQLite)
docker compose up -d --scale web=3            # várias instâncias; o serviço proxy distribui (least_conn)
docker compose --profile redis up -d          # + Redis (REDIS_URL=redis://redis:6379/0 e RATELIMIT_STORAGE_URI igual)
docker compose --profile postgres up -d       # + PostgreSQL (defina POSTGRES_PASSWORD e DATABASE_URL)
```

Serviços: `migrar` (roda uma vez por deploy: backup, migrations, seed da loja; os demais esperam por ele), `web` (gunicorn, `/healthz` como healthcheck, escalável), `proxy` (nginx), `worker` (`flask jobs-worker`, consome a fila de e-mails e imagens), `tarefas` (rotina periódica) e, por perfil, `redis` e `postgres`. Volumes: `banco` (`/srv/instance`) e `uploads` (`/srv/app/static/data`).

`docker compose config` valida o arquivo, mas `docker build`/`up` NÃO foram executados neste ambiente (sem daemon): rode num host com Docker antes do deploy (ver pendências).

## 5.1 Desempenho e escala

| Recurso | Como usar |
|---|---|
| Cache (Redis ou memória) | `REDIS_URL`. Sem Redis cada processo tem seu cache; as invalidações só valem por processo. Com mais de 1 instância, use Redis. |
| Fila de jobs | `JOBS_MODE=queue` + `flask --app main jobs-worker` (um ou mais). Em `eager` (padrão) o e-mail é enviado na requisição. Jobs com falha tentam de novo com espera crescente; presos há 10 min voltam para a fila. |
| Estáticos | URL com hash do conteúdo, cache de 1 ano (`immutable`), Brotli/Gzip. `CDN_URL=https://cdn.exemplo.com` reescreve `/static` para o CDN; o CDN deve ter este app (ou o nginx) como origem, repassar `Access-Control-Allow-Origin` (o app já envia) e respeitar `Cache-Control`. O CSP acompanha o `CDN_URL`. |
| Imagens | Uploads novos viram WebP reduzido. `flask --app main imagens-otimizar` (simulação) e `--aplicar` convertem os antigos. AVIF não é usado: o ganho sobre WebP é pequeno e o suporte em Pillow depende do build. |
| Banco | Índices para as consultas frequentes (migration `d4e5f6a7b8c9`), testados com `EXPLAIN QUERY PLAN`; guarda contra N+1 nos testes. Pool e timeouts por `DB_*` (PostgreSQL). Total de conexões = instâncias x workers x (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`): confira o `max_connections` do banco. Coloque o banco na mesma região/rede do app: cada requisição faz várias consultas e a latência de rede multiplica. |
| Várias instâncias | `deploy/nginx.conf` (upstream com `least_conn`). SQLite só funciona com todas no mesmo servidor e mesmo volume; vários servidores exigem PostgreSQL, Redis e volume de uploads compartilhado (ou armazenamento de objetos). |
| Observabilidade | `/healthz`; log de requisições lentas (`SLOW_REQUEST_MS`); métricas de usuários reais (Core Web Vitals p75 em `/admin/desempenho`, anônimas, `RUM_*`); OpenTelemetry opcional (`requirements-otel.txt`, `OTEL_*`). |
| Interface | Esqueletos de carregamento, busca com debounce e cancelamento, autocompletar, paginação por cursor, envio otimista (chat, notificações), KaTeX só quando há fórmula, `content-visibility` em listas longas. |

## 6. Testes e CI

`python -m pytest -q` roda tudo em banco em memória, sem rede. O CI (`.github/workflows/ci.yml`) roda os testes e `pip-audit`.
