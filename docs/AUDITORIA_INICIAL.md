# ExQuest — Auditoria Inicial

Data: 2026-11-10 · Base auditada: `ExQuest.zip` enviado pelo proprietário (173 arquivos, 24 MB, 3 migrations, `instance/database.db` com 27 tabelas).

**Como foi feito.** Leitura integral de `app/__init__.py`, `app/models.py`, `app/forms.py`, `app/security.py`, `app/views.py` (2.522 linhas, 75 rotas), `migrations/`, `requirements.txt`, `.gitignore`, `.env` (somente o formato, nunca os valores), `README.md`, dos templates, JS e CSS (por varredura estatística + leitura dos arquivos críticos) e do banco real (esquema, contagens e dados). O app original foi executado **em cópias do banco** (nunca no original) com 41 requisições GET e testes de exploração direcionados. Itens marcados **[confirmado]** foram reproduzidos; **[código]** foram identificados por leitura e serão cobertos por teste na correção.

**Carga assumida.** Produto educacional com comunidade: de centenas a alguns milhares de usuários simultâneos, vários processos de aplicação, dinheiro real (Premium e moedas) — portanto concorrência, idempotência e autenticação de webhook são requisitos, não opcionais.

---

## 1. Resumo executivo

O ExQuest tem boas ideias e o esqueleto de um produto completo, mas **hoje não pode receber dinheiro real nem usuários reais**: qualquer pessoa, sem login, consegue conceder Premium Avançado a si mesma ou creditar moedas; o ranking e a economia podem ser inflados repetindo a mesma resposta; o módulo de competições nunca funcionou (modelo e rotas discordam); e o esquema do banco não pode ser recriado a partir das migrations. A interface depende de ~900 estilos inline, centenas de emojis e não tem nenhum teste automatizado.

| Gravidade | Qtde | Significado |
|---|---|---|
| P0 | 9 | Crítico: perda de dinheiro/dados, exploração trivial, produto quebrado |
| P1 | 17 | Alto: segurança, integridade ou regra de negócio incorreta |
| P2 | 13 | Moderado: manutenção, desempenho, UX, acessibilidade |
| P3 | 8 | Melhorias |

---

## 2. Mapa da arquitetura atual

```
main.py ──> app/__init__.py:create_app()
              ├─ extensões globais: db, migrate, login_manager, bcrypt, csrf, mail
              ├─ headers de segurança (after_request) + CSP com 'unsafe-inline'
              ├─ context processor: avatar_display, nick_html, banner_url (HTML montado em Python)
              └─ with app_context(): db.create_all() + _safe_add_columns() + _seed_loja_inicial()   <-- a cada inicialização
app/views.py  (1 único Blueprint "main", 75 rotas, 89 funções)
app/models.py (27 modelos; regras de negócio embutidas: planos, limites, níveis, boosts)
app/forms.py  (Flask-WTF)    app/security.py (sanitização, "moderação", logs)
app/templates/ (40 HTML, base.html sem DOCTYPE)   app/static/{css/main.css 1.802 linhas, js/*.js 7 arquivos, vendor/katex, data/ (uploads + 3 badges oficiais), img/}
migrations/   (Alembic: 3 revisões, cadeia NÃO autossuficiente)
instance/database.db (SQLite)   .env (credenciais reais no zip)
```

| Domínio | Rotas (aprox.) | Onde vive hoje |
|---|---|---|
| Auth (registro, login, Google, recuperação) | 8 | views.py L246-453 |
| Dashboard / Perfil / Edição | 8 | L459-670 |
| Questões / Simulados / API de resposta | 5 | L676-925 |
| Ranking | 1 | L931-974 |
| Loja / Inventário / Moedas | 7 | L980-1038, 2040-2102 |
| Premium / Pagamentos / Trial | 8 | L1044-1214, 2122-2159 |
| Social (amigos, grupos, chat, DM) | 18 | L1220-1558, 2191-2371 |
| Competições | 5 | L1801-2033 |
| Admin | 11 | L1564-1730 |
| Ads | 2 | L1747-1794 |
| Desempenho (API de gráficos) | 1 | L2378-2480 |

**Serviços externos:** SMTP (Flask-Mail, falha silenciosa), Google OAuth (Authlib — **ausente do requirements.txt**), Mercado Pago/Stripe (**inexistentes**: só um `TODO` e webhooks sem verificação), OpenAI (**não utilizado**; a avaliação discursiva é TF-IDF local rotulada como "IA"), Socket.IO (**não utilizado**; o chat recarrega a página).

**Dependências:** 64 pacotes pinados; ≥ 18 sem uso no código (openai, httpx/httpcore/h11, Flask-SocketIO, python-socketio/engineio, simple-websocket, wsproto, eventlet, pyotp, python-magic, rich/pygments/markdown-it/mdurl, tqdm, colorama, distro, `dotenv` + `python-dotenv` duplicados, Flask-Limiter instalado mas não usado) e 1 faltando (**authlib**).

---

## 3. Achados

Formato: **ID — título** · arquivos · *consequência* · **solução** · fase.

### P0 — Críticos

**P0-01 — Webhook de Premium sem autenticação [confirmado]** · `views.py` L1185-1214
`POST /premium/webhook` aceita JSON anônimo (`{"id":"x","plano":"advan","usuario_id":2,"ciclo":"anual"}`) e ativa o plano. Reproduzido: usuário gratuito virou `advan`. *Premium (e o dinheiro dele) é gratuito para qualquer pessoa.* **Solução:** remover; novo endpoint por provedor com verificação criptográfica da assinatura, consulta ao provedor, conferência de usuário/produto/valor/moeda e idempotência. Fase 4.

**P0-02 — Webhook de moedas sem autenticação e não idempotente [confirmado]** · `views.py` L2086-2102
`POST /loja/moedas/webhook {"compra_id":1}` creditou **1.500 moedas** ao administrador sem pagamento; o teste `status == 'pago'` e a atualização não são atômicos (duplo envio concorrente credita duas vezes). **Solução:** igual a P0-01 + crédito via ledger com chave de idempotência única. Fase 4.

**P0-03 — Premium ativado sem pagamento [confirmado]** · `views.py` L1098-1174, 2122-2136
`POST /premium/assinar/<plano>/<ciclo>` e `/premium/trocar/...` gravam histórico "pago" e ativam o plano na hora ("modo simulado"); `trial_aceitar` não revalida elegibilidade e pode **rebaixar** quem já assinou. **Solução:** assinatura só nasce de pagamento confirmado pelo provedor; sem provedor configurado a tela informa "indisponível até configurar" em vez de simular. Fase 4.

**P0-04 — XSS armazenado no nick [confirmado]** · `app/__init__.py` L122-129, `models.py` L240-249
`nick_gradiente`/`nick_cor` (texto livre) vão crus para `style="..."` dentro de `Markup(...)`. Reproduzido: `red" onmouseover="alert(1)" x="` vira atributo de evento no perfil e na barra lateral de **todos** que virem o usuário. CSP permite `unsafe-inline`. Combinado com P0-03, qualquer usuário chega ao campo. **Solução:** validar cor (`#RRGGBB`) e gradiente (conjunto de paradas validadas) no servidor, renderizar por classes/variáveis CSS escapadas, remover `unsafe-inline` da CSP. Fases 2/5.

**P0-05 — Segredos expostos e configuração insegura** · `.env` (no zip), `app/__init__.py` L26, `main.py`, `app_secrets.py`
O `.env` enviado contém valores preenchidos para SECRET_KEY, senha SMTP, Google client secret, chave OpenAI e `MP_ACCESS_TOKEN` (74 caracteres). O código aceita `SECRET_KEY` padrão `dev-secret`; `main.py` roda `debug=True` (console Werkzeug = execução remota se exposto); cookies `Secure=False`; HSTS enviado até em HTTP. **Ação do proprietário:** como o `.env` trafegou dentro de um zip, **rotacionar** as chaves reais (SMTP, Google, OpenAI, Mercado Pago, SECRET_KEY). **Solução no código:** `Config` por ambiente que se recusa a iniciar em produção sem SECRET_KEY forte, `.env.example` sem credenciais, remover `app_secrets.py`. Fase 2.

**P0-06 — Farm infinito de XP e moedas [confirmado]** · `views.py` L765-863
Responder a mesma questão 5 vezes rendeu +104 XP; não existe unicidade por (usuário, questão), e `tempo_segundos` (usado no "anti-cheat") vem do cliente. **Solução:** recompensa integral só na 1ª resposta correta de cada questão (repetições dão fração/zero), tempo medido no servidor a partir do momento em que a questão foi entregue, XP/moedas via ledger/UPDATE atômico. Fase 3/4.

**P0-07 — Saldo de moedas sujeito a condições de corrida** · `views.py` L991-1006 e todos os `usuario.moedas += x`
Leitura→soma→escrita no ORM perde atualizações: dois cliques rápidos em "Comprar" podem gastar uma vez e entregar duas, ou deixar saldo negativo. **Solução:** ledger imutável + `UPDATE usuarios SET moedas = moedas - :p WHERE id=:id AND moedas >= :p` dentro de transação, com chave de idempotência. Fase 4.

**P0-08 — Evolução de esquema quebrada** · `migrations/`, `app/__init__.py` L139-167
(a) A 1ª migration (`550c87642fa5`, `down_revision=None`) só faz `ADD COLUMN` em tabelas que ela não cria — `flask db upgrade` num banco vazio falha. (b) `_safe_add_columns` inspeciona a tabela `usuario` (a real é `usuarios`), então não faz nada e esconde o erro com `except: pass`. (c) `db.create_all()` + seed rodam na importação do app a cada start. (d) Arquivos de migration com acento corrompido no zip. **Solução:** baseline que recria o esquema pré-1.4, cadeia única Alembic, remover create_all/seed da inicialização (seed vira comando CLI idempotente), testar upgrade em banco vazio **e** em cópia do banco real. Fase 2.

**P0-09 — Competições nunca funcionaram [código]** · `models.py` L618-657, `views.py` L1801-2033, `forms.py` L165-212
O modelo `Torneio` usa `materias_json`/`dificuldades_json`; as rotas e o formulário usam `materia_id`/`dificuldade` inexistentes → `admin_novo_torneio` levanta `TypeError`, `competicao_detalhe` levanta `AttributeError`. Além disso: as questões sorteiam de novo a cada recarga (cada participante vê um conjunto diferente), não há cronômetro nem janela de tempo no envio, a finalização é manual, prêmios são creditados direto em `xp/moedas`, e o limite mensal do plano Intermediário usa mês sem ano. A tabela `torneios` tem 0 linhas — nunca foi usada. **Solução:** reimplementar com questões fixas por torneio (tabela de ligação), tempo validado no servidor, finalização automática idempotente, prêmios pelo ledger. Fase 7.

### P1 — Altos

**P1-01 — Redirecionamento aberto no login [confirmado]** · `views.py` L310: `next=https://evil.example` → `Location` externo. **Solução:** aceitar apenas caminhos relativos locais. Fase 2.

**P1-02 — Banimento não derruba a sessão [confirmado]** · `models.py` L6-8, `views.py` L303/395: usuário banido continua acessando `/dashboard`; login Google ignora `is_banido`. **Solução:** `user_loader` e `before_request` rejeitam banidos; versão de sessão invalidável. Fase 2.

**P1-03 — Banimento automático por heurística** · `views.py` L183-240, 788-806: a conta é suspensa automaticamente (`pontuacao >= 10`) com base em tempos fornecidos pelo cliente. Falso positivo derruba usuário legítimo e contradiz a especificação. **Solução:** heurística apenas **sinaliza** para revisão administrativa (fila de moderação com evidências), nunca pune sozinha. Fase 3.

**P1-04 — Login Google inseguro e quebrado na instalação limpa** · `views.py` L329-400: `authlib` não está no requirements; vincula contas por e-mail sem checar `email_verified` (tomada de conta); cria cliente OAuth a cada request; engole qualquer exceção; não checa banimento. **Solução:** Authlib registrado uma vez, exige `email_verified`, vincula por `google_id` e só por e-mail verificado, valida ban. Fase 2.

**P1-05 — Proteção contra força bruta em memória** · `views.py` L279-318: dicionário por processo (some no restart, não é compartilhado entre workers); Flask-Limiter instalado e não usado; sem limite em registro, recuperação, APIs, envio de mensagens. **Solução:** Flask-Limiter (já dependência) com storage configurável + limites por rota e por conta. Fase 2.

**P1-06 — Recuperação de senha** · `views.py` L404-453: token guardado em claro; falha de e-mail engolida sem log; reset não invalida sessões; senha mínima de 6; sem limite de pedidos. **Solução:** guardar hash SHA-256 do token, log estruturado da falha de envio, versão de sessão, política de senha melhor, rate limit. Fase 2.

**P1-07 — Uploads: validação fraca e arquivos privados públicos** · `security.py` L101-116, `views.py` L53-64, 1458-1532
Qualquer arquivo começando com `RIFF` é aceito como WebP; anexos de chat (`.pdf/.doc/.docx/.zip/.txt`) são validados só pela extensão; todos os uploads — inclusive arquivos de conversas privadas — ficam em `/static/data/...`, acessíveis sem login [confirmado: `chat_files/*.jpg` responde 200 anônimo]; limite do chat (10 MB) é inalcançável pois `MAX_CONTENT_LENGTH` = 8 MB. **Solução:** validar conteúdo real com Pillow (decodificar/reencodar imagens), assinatura de PDF/ZIP, servir anexos de chat por rota autenticada com checagem de membro, uploads fora de `static`. Fase 2.

**P1-08 — Benefícios Premium não impostos no servidor** · `views.py` L53-64, 606-621; `models.py`: GIF no avatar (benefício Básico) é aceito para todos; limite diário de questões é checado só quando o cliente envia `modo='questao'` — enviando `modo='simulado'` o limite é ignorado [código]; simulado não tem sessão no servidor. **Solução:** serviço de direitos (`entitlements`) único; modo deduzido no servidor; sessão de simulado persistida. Fase 3/4.

**P1-09 — Autorização/abuso em grupos e amizades** · `views.py` L1285-1302, 2244-2287: `social_adicionar` não valida que o destinatário existe; `grupo_config` permite ao admin do grupo adicionar **qualquer** id de usuário (sem amizade nem consentimento) e não valida existência; `admin_banir` permite banir a si mesmo ou outros admins; sem bloqueio de usuários, sem denúncia. **Solução:** serviço social com regras explícitas, bloqueios e denúncias. Fase 7.

**P1-10 — Exclusões em cascata destroem histórico** · `models.py` L368-372, 387-390: excluir uma matéria apaga suas questões e **todas as respostas de todos os usuários** (ranking e estatísticas mudam silenciosamente) sem confirmação de impacto. **Solução:** arquivamento (soft-delete) de matérias/questões; exclusão só quando sem respostas; confirmação com contagem. Fase 3.

**P1-11 — Duas páginas com erro 500 [confirmado]** · `/ranking?materia_id=N` (`views.py` L943-957: subquery tratada como objeto `Usuario`) e `/social/sugestoes` (L2350-2354: `Usuario.nivel` é `@property` Python usada em filtro SQL). **Solução:** consultas reescritas; coluna/expressão de nível calculada no SQL. Fase 3.

**P1-12 — Datas e fuso horário** · `models.py`, `views.py`: `date.today()` do servidor define limites diários/streak/gráficos; datetimes gravados "naive" em UTC e relidos sem tz; `ultimo_reset_torneios.month` ignora o ano; streak só avança quando acerta (não quando estuda); `Escudo Duplo` (valor 2) nunca implementado — protege 1 dia; consumíveis podem ser "usados" sem checar `quantidade > 0` e boosts **sobrescrevem** em vez de estender. **Solução:** fuso America/Sao_Paulo único (`clock` service), streak por atividade, shield com cargas. Fase 3/4.

**P1-13 — Moderação de texto gera falsos positivos e não protege** · `security.py` L15-58 [confirmado]: bloqueia "armazenamento", "alarmante", "desarmar", "bomba de calor", e qualquer texto com `;` ou `--` ("Calcule a integral; depois derive"), inclusive o enunciado de questões de matemática/física. A "detecção de SQL injection" por regex é inútil (o ORM parametriza) e atrapalha. **Solução:** remover regex de "ataque", manter escape de saída + limites de tamanho; filtro de palavrões apenas em chat, por lista de palavras inteiras, com preferência do usuário. Fase 3.

**P1-14 — `sanitizar_texto` corrompe conteúdo [confirmado]** · `security.py` L34-40: `bleach.clean` converte `&`→`&amp;`, `<`→`&lt;` e o Jinja escapa de novo: "x < 3" aparece como `x &lt; 3`, quebrando LaTeX/KaTeX nas questões. **Solução:** armazenar texto puro (validado/limitado), escapar só na saída. Fase 3.

**P1-15 — Sem restrições de unicidade/FK/índices** · `models.py`, banco: nenhum UNIQUE em (usuário,item) do inventário, par de amizade, membro de grupo, participante de torneio, recompensa de nível; **nenhum índice** em FKs (`respostas_usuarios.usuario_id`, `mensagens.grupo_id`…); SQLite roda com `foreign_keys=OFF`. Duplicatas por corrida são possíveis. **Solução:** migration com UNIQUEs (após deduplicação segura) + índices + `PRAGMA foreign_keys=ON` na conexão. Fase 2/8.

**P1-16 — Escritas em requisições GET** · `views.py` L459-507: o dashboard cria ofertas de trial e concede recompensas de nível dentro de um GET; sob concorrência concede duas vezes (sem unicidade). **Solução:** concessão idempotente no ponto do evento (ganho de XP). Fase 3.

**P1-17 — Cabeçalhos/CSP/CSRF** · `__init__.py` L64-87: CSP com `'unsafe-inline'` em scripts; Chart.js de CDN sem SRI; `GET /logout` (CSRF de logout); HSTS sempre; X-XSS-Protection obsoleto. **Solução:** CSP por nonce, assets locais, logout por POST, HSTS só em produção. Fase 2/5.

### P2 — Moderados

**P2-01 — `views.py` monolítico**: 2.522 linhas, 98 comentários `# pyrefly: ignore`, imports no meio das funções, `grupo_chat` e `grupo_chat_slug` duplicados, planos/limites definidos em 3 lugares. → Blueprints por domínio + services. Fase 3.
**P2-02 — N+1 e consultas ineficientes**: dashboard (1 consulta por matéria + `.all()` de ids), `_gerar_dados_grafico` e `/api/desempenho` (~130 consultas por chamada), ranking carrega todos os ids para achar a posição, `usuario.total_respostas` dispara 2 COUNTs, `social` consulta por amigo. → agregações SQL, cache curto. Fase 3/8.
**P2-03 — Dependências**: ver mapa. → remover ≥ 18 pacotes, adicionar authlib, requirements enxuto + versões de dev separadas. Fase 8.
**P2-04 — Emojis e identidade visual**: centenas de emojis Unicode e entidades numéricas (`&#x1F3C6;`) em 45 arquivos; emojis gravados no banco (`materias.icone`, `grupos_chat.icone`); avatares predefinidos são emojis. → ícones SVG; migração com compatibilidade (ver ADR-004). Fase 5/6.
**P2-05 — CSS/HTML**: `main.css` com ~900 estilos inline replicados nos templates, 155 handlers `onclick=` inline, `base.html` sem `<!DOCTYPE>`/`<html lang>` (modo quirks), `@import` de Google Fonts bloqueando render e carregando 5 famílias (Orbitron/Pacifico/Playfair só para nick). → design system, fontes locais. Fase 5.
**P2-06 — Acessibilidade**: sem skip-link, sem foco visível padronizado, modais sem trap de foco/`role="dialog"`, ícones emoji sem rótulo, contraste de `--text-dim` (#475569 sobre #07090f ≈ 2,3:1) abaixo de AA. Fase 5/6.
**P2-07 — Anúncios simulados**: o "vídeo" de 15 s é um placeholder e o servidor concede +2 questões a quem apenas faz o POST (até 3×/dia) — demonstração apresentada como funcionalidade real. → substituir por bônus ligados a missões/atividade real (ADR-006). Fase 7.
**P2-08 — "IA" discursiva é TF-IDF**: rotulada como IA, nota heurística; chave OpenAI do `.env` não é usada. → manter avaliador local honesto ("correspondência com o gabarito") e adicionar provedor OpenAI opcional com fallback. Fase 7.
**P2-09 — Histórico de pagamentos guarda campos de cartão** (`pagamento_historico.cartao_*`): nunca preenchidos, risco PCI se usados. → parar de usar, manter colunas (sem DROP), documentar. Fase 4.
**P2-10 — Trial**: aceitar não revalida elegibilidade (pode rebaixar assinante). → serviço Premium único. Fase 4.
**P2-11 — Tags de usuário**: 5 dígitos (100k espaço) com laço sem limite; `tag_custom` sem validação de formato. Fase 3.
**P2-12 — Erros engolidos**: 11 `except Exception: pass` (e-mail, dashboard, trial, nível). → logs estruturados. Fase 3.
**P2-13 — Seed da loja ≠ banco real**: o seed (29 itens) só roda com tabela vazia; o banco tem 19 itens diferentes (ex.: `efeito-particles`, que o JS não reconhece e cai no `else` genérico). → catálogo versionado com upsert idempotente por `slug`. Fase 4.

### P3 — Melhorias

**P3-01** Zero testes, zero CI, sem Docker. **P3-02** Sem SEO técnico (meta description, OG, canonical, sitemap, robots, JSON-LD). **P3-03** Sem health check, sem logs estruturados, sem rotina de backup. **P3-04** README instrui o usuário a **substituir rotas manualmente** no código (obsoleto). **P3-05** `__pycache__` de CPython 3.14 no zip e arquivos de migration com nomes acentuados corrompidos. **P3-06** `.gitignore` não cobre `app/static/data/bordas|efeitos|loja|badges_loja` e deixa os 3 badges oficiais dentro da pasta de uploads. **P3-07** Sem notificações, missões, revisão espaçada, caderno de erros, favoritos, relatórios. **P3-08** Chat sem tempo real (recarrega a página).

---

## 4. Auditoria funcional (resumo por funcionalidade)

| Funcionalidade | Deveria | Faz hoje | Principais problemas |
|---|---|---|---|
| Registro/Login | Criar conta e autenticar com segurança | Funciona; `next` aberto; força bruta em memória | P0-05, P1-01/02/05 |
| Google OAuth | Login social | Quebra sem authlib; vincula por e-mail não verificado | P1-04 |
| Recuperação de senha | Link por e-mail, expira | Funciona se SMTP ok; token em claro | P1-06 |
| XP/Níveis | Progressão justa | Níveis corretos; XP farmável; nível em SQL impossível | P0-06, P1-11 |
| Streak | Dias consecutivos de estudo | Só avança ao acertar; shield parcial | P1-12 |
| Questões / Simulados | Resolver com limites do plano | Limite burlável; sem sessão de simulado; resultado calculado no cliente | P1-08 |
| Discursivas | Avaliar resposta aberta | TF-IDF local rotulado "IA" | P2-08 |
| Ranking | Posições por XP/matéria | Geral ok (lento); por matéria = 500 | P1-11, P2-02 |
| Loja/Inventário | Comprar com moedas e equipar | Corrida de saldo; boosts sobrescrevem; fundo de perfil cobre o banner | P0-07, P1-12, §5 |
| Moedas (dinheiro real) | Comprar pacotes | Webhook aberto; sem gateway | P0-02 |
| Premium | Assinar, renovar, cancelar | Ativa sem pagar; webhook aberto | P0-01/03 |
| Social/Chat | Amizades, grupos, DMs | Funciona; arquivos públicos; sem bloqueio/denúncia | P1-07/09 |
| Competições | Torneios com ranking e prêmios | Quebrado (modelo ≠ rotas) | P0-09 |
| Admin | Gerir conteúdo e usuários | Sem paginação, sem auditoria de ações, exclusão destrutiva | P1-10 |
| Anúncios | Questões extras por anúncio | Simulado | P2-07 |

## 5. O problema dos "fundos de perfil" (referência visual)

As duas imagens de referência mostram: (1) no modal de pré-visualização, o "Efeito Aurora" pintado **no lugar do banner**, com o avatar sobreposto; (2) na página de perfil, regiões marcadas em vermelho — as **margens laterais e os vãos entre os cards** (esquerda e direita da pilha de cards e as faixas entre "card principal", "Nível" e "Desempenho"). A leitura adotada: o fundo de perfil é uma camada de **palco** posicionada **atrás** do card principal e dos demais cards do perfil, visível nessas margens e vãos; o banner continua independente dentro do card; o fundo nunca cobre textos, avatar, botões nem a barra lateral. Hoje o código desenha o efeito sobre o card inteiro (`perfil-efeito-layer`, `inset:0`) e a pré-visualização o desenha na área do banner (`loja_preview.js`). A correção e as previews serão feitas sobre essa mesma estrutura (`.perfil-stage`) para que o preview seja idêntico ao resultado real. Se a leitura estiver diferente do pretendido, o ajuste é de CSS num único componente.

## 6. Auditoria visual (resumo)

Tema "dark glassmorphism" com gradiente índigo→rosa repetido em botões, barras, textos e cards; pilha de cards idênticos (`.card`) em todas as páginas; mesma hierarquia tipográfica; emojis como ícones (inconsistentes entre sistemas operacionais); estilos inline para espaçamento/cor em praticamente todo elemento (impossibilita tema e consistência); animações `animate-in` genéricas; o perfil usa ~80 estilos inline; páginas de erro e autenticação sem identidade; tabelas administrativas sem paginação/filtros; sem estados de carregamento/vazio/erro padronizados; responsividade resolvida caso a caso (sidebar fixa 260 px).

## 7. O que NÃO foi lido/verificado

- Compatibilidade real com Python 3.14 (ambiente da auditoria: 3.13; os pins do `requirements.txt` instalaram normalmente).
- Conteúdo integral de cada template (lidos `base.html`, `perfil.html`; os demais por varredura estatística e serão lidos ao serem reescritos).
- Fluxos de pagamento reais (nenhum provedor está integrado) e Google OAuth/SMTP ao vivo (sem credenciais de teste).
- Desempenho sob carga real (sem ferramenta de carga; as conclusões de escala vêm de leitura de código).

## 8. Ordem de implementação

1. **Fase 2** — P0-04/05/08, P1-01/02/04/05/06/07/15/17 (segurança, migrations, uploads, config).
2. **Fase 3** — P0-06, P1-03/08/10/11/12/13/14/16, P2-01/02/11/12 (modularização e regras).
3. **Fase 4** — P0-01/02/03/07, P2-09/10/13 (ledger, loja, pagamentos, Premium).
4. **Fases 5-6** — P2-04/05/06 (design system, sem emojis, todas as páginas).
5. **Fase 7** — P0-09, P1-09, P2-07/08, P3-07/08 (competições, social, missões, revisão espaçada…).
6. **Fases 8-10** — performance, SEO, DevOps, documentação, testes finais.
