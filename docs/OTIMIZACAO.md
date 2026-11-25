# Otimização: estado item a item (2026-11-22)

Legenda: **Feito e testado** (teste automatizado ou navegador real) | **Precisa de infraestrutura sua** (código pronto, serviço externo a contratar) | **Não executado aqui** | **Não se aplica**.

| # | Item | Estado | Onde / como |
|---|---|---|---|
| 1 | Esqueletos de carregamento | Feito e testado (Chromium) | `components.css`, `app.js`, `chat.js` |
| 2 | Imagens WebP/AVIF | WebP feito e testado; AVIF não usado (ganho pequeno sobre WebP, suporte do Pillow varia) | `services/uploads.py`, `flask imagens-otimizar` |
| 3 | Evitar chamadas duplicadas | Feito e testado | `window.exq` (GET em andamento reaproveitado), cancelamento com AbortController, preload de fonte corrigido (baixava 2x) |
| 4 | Debounce na busca e autocompletar | Feito e testado (Chromium) | `data-busca-viva`, `/questoes/sugestoes` |
| 5 | Paginação das listas e da API | Feito e testado | cursor `antes=` no chat, páginas no ranking e no admin |
| 6 | Estáticos por CDN | Código pronto; **precisa de CDN sua** | `CDN_URL`, CSP e CORS acompanham; guia em `GUIA_DE_INSTALACAO_E_DESENVOLVIMENTO.md` |
| 7 | Tarefas lentas em fila | Feito e testado | tabela `jobs`, `flask jobs-worker`, `JOBS_MODE=queue` |
| 8 | Corrigir N+1 | Feito e testado | `tests/test_consultas.py` compara 3 e 20 itens |
| 9 | Brotli/Gzip | Feito e testado | Flask-Compress; HTML só em GET sem query (mitiga BREACH) |
| 10 | Cache Redis | Feito e testado com Redis real; **Redis em produção é seu** | `app/cache.py`, `REDIS_URL` |
| 11 | Remover dependências sem uso | Feito | Flask-Mail removido; instalação em venv limpo validada |
| 12 | Timeout nas APIs externas | Feito e testado | `providers/http.py`, Google, SMTP |
| 13 | Interface otimista | Feito e testado (Chromium) | chat (confirma e desfaz), notificações |
| 14 | Lazy loading de imagens | Feito | `loading="lazy"`, `decoding="async"` |
| 15 | Requisições independentes em paralelo | Não se aplica: a interface atual não tem requisições independentes em sequência | |
| 16 | Índices | Feito e testado | 3 migrations; `EXPLAIN QUERY PLAN` em teste |
| 17 | Rastrear requisições lentas (OpenTelemetry) | Feito; coletor OTLP é seu | `app/telemetry.py`, `requirements-otel.txt`, log `SLOW_REQUEST_MS` |
| 18 | Servidor perto do banco | Documentado; **depende da sua hospedagem** | Postgres na mesma região (`--profile postgres`) |
| 19 | Renderizar no servidor | Já é o modelo do app (Jinja); fragmentos parciais para listas | |
| 20 | Scripts de terceiros depois da página | Não se aplica: não há scripts de terceiros; KaTeX é local e sob demanda | |
| 21 | Dividir o JS por página | Feito: KaTeX, chat e RUM carregam só onde usados | |
| 22 | Virtualizar listas longas | Equivalente: `content-visibility:auto`, paginação e poda do chat a 300 mensagens | |
| 23 | Colunas necessárias | Feito e testado | `load_only` nas listas pesadas |
| 24 | Pool de conexões | Feito e testado (configuração); efeito só em PostgreSQL | `DB_POOL_*` |
| 25 | Evitar re-renders | Não se aplica a React; app SSR. Equivalente: atualização pontual de DOM | |
| 26 | Cache dos estáticos no navegador | Feito e testado | hash na URL, `immutable`, 1 ano |
| 27 | Tráfego entre várias instâncias | Configuração pronta e validada com `docker compose config`; **não executada** (sem Docker aqui) | `docker-compose.yml`, `deploy/nginx*.conf` |
| 28 | Fontes locais e com limite de peso | Feito e testado | teste de orçamento: pré-carregadas ≤ 100 KB, só woff2, `font-display: swap` |
| 29 | Monitorar usuários reais | Feito e testado | `/admin/desempenho` (LCP, CLS, INP, p75, anônimo) |
| 30 | Testar em celulares e redes lentas | Emulação feita; aparelhos reais não | abaixo |

## Medição (Chromium, celular 390 px, CPU 4x mais lenta)
Página inicial, cache vazio: transferência caiu de 215 KB para 128 KB depois de corrigir o download duplicado das fontes. Rede 3G lenta: FCP 1,6 s e CLS 0,03 antes da correção (re-medição completa não repetida). Páginas autenticadas com cache aquecido: cerca de 9 KB. Medida de emulação, não de aparelho real: use `/admin/desempenho` após o deploy.
