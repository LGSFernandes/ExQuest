# ExQuest

**Plataforma educacional gamificada para prática, acompanhamento de desempenho e interação entre estudantes.**

![Logo do ExQuest](app/static/img/logo.png)

O ExQuest reúne questões, simulados, acompanhamento de evolução, recompensas, personalização de perfil e recursos sociais em uma aplicação web. A proposta é tornar a rotina de estudos mais organizada e motivadora, sem perder o foco no aprendizado.

> **Status do repositório:** projeto em desenvolvimento. Este README descreve o código presente na versão documentada; recursos que dependem de integração externa ou ainda possuem implementação provisória estão identificados como tal.

---

## Sumário

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Tecnologias](#tecnologias)
- [Arquitetura atual](#arquitetura-atual)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Domínio e dados](#domínio-e-dados)
- [Rotas principais](#rotas-principais)
- [Configuração e execução local](#configuração-e-execução-local)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Banco de dados e migrations](#banco-de-dados-e-migrations)
- [Arquivos enviados e assets](#arquivos-enviados-e-assets)
- [Segurança e privacidade](#segurança-e-privacidade)
- [Integrações e limitações conhecidas](#integrações-e-limitações-conhecidas)
- [Administração](#administração)
- [Testes e qualidade](#testes-e-qualidade)
- [Execução em produção](#execução-em-produção)
- [Documentação complementar](#documentação-complementar)
- [Licença e propriedade intelectual](#licença-e-propriedade-intelectual)

---

## Visão geral

O ExQuest foi desenvolvido em Python com Flask e utiliza templates Jinja, CSS e JavaScript para entregar uma aplicação web integrada a um banco de dados relacional.

A plataforma contempla quatro áreas principais:

1. **Aprendizado:** catálogo de matérias e questões, simulados e registro de respostas.
2. **Progressão:** XP, níveis, streaks, recompensas, estatísticas e ranking.
3. **Personalização e economia virtual:** moedas internas, loja, inventário e elementos cosméticos de perfil.
4. **Comunidade e gestão:** amizades, grupos, mensagens, competições e painel administrativo.

O código atual deve ser tratado como uma base de desenvolvimento. A presença de uma tela ou rota não significa, por si só, que uma integração externa esteja pronta para uso comercial ou produção.

## Funcionalidades

### Conta e autenticação

- Cadastro e login com credenciais locais.
- Sessão de usuário com Flask-Login.
- Alteração e recuperação de senha por e-mail, quando o SMTP estiver configurado.
- Login com Google OAuth, condicionado à configuração das credenciais e à instalação da dependência opcional necessária.
- Perfil público identificado por nome de usuário.

### Perfil e personalização

- Edição de informações pessoais e biografia.
- Upload de avatar e banner.
- Preferências de privacidade para estatísticas, histórico e lista de amigos.
- Preferência para bloquear solicitações de amizade.
- Personalização de elementos do nome e do perfil associada aos recursos Premium e à loja.
- Exibição de informações de progresso e desempenho.

### Questões e simulados

- Catálogo de questões associado a matérias.
- Questões de múltipla escolha e discursivas.
- Níveis de dificuldade.
- Alternativas e gabaritos para questões objetivas.
- Campo de resposta esperada para questões discursivas.
- Registro de respostas e sessões de simulado.
- Recompensas de XP e moedas conforme as regras do projeto.
- Suporte a expressões matemáticas em LaTeX por meio do KaTeX hospedado localmente.

**Avaliação discursiva:** a implementação atual utiliza comparação textual local, com similaridade baseada em TF-IDF simplificado, Jaccard e heurísticas de cobertura de termos. Ela não equivale à avaliação semântica de um modelo de linguagem e pode produzir falsos positivos ou falsos negativos. Resultados automáticos devem ser tratados como estimativas de apoio, não como correção pedagógica infalível.

### Progressão e gamificação

- Pontos de experiência (XP) e níveis.
- Streak de atividade.
- Recompensas por progressão de nível.
- Boosters de XP e moedas.
- Créditos internos relacionados à experiência de anúncios.
- Ranking de usuários.
- Registros de respostas e desempenho.

### Loja, moedas e inventário

- Carteira de moedas virtuais mantida na conta do usuário.
- Catálogo de itens da loja.
- Itens cosméticos, bordas e efeitos de perfil.
- Compra de itens utilizando a moeda interna.
- Inventário e ativação de itens adquiridos.
- Pacotes de moedas apresentados em uma página separada.

**Importante:** comprar itens com moedas internas é diferente de comprar moedas com dinheiro real. Na versão analisada, o fluxo de compra de pacotes de moedas ainda contém um ponto de integração pendente com gateway de pagamento. Não considere uma solicitação criada como pagamento concluído.

### Premium e pagamentos

- Página de apresentação de planos.
- Controle local de plano, ciclo, expiração e cancelamento agendado.
- Histórico de registros de pagamento.
- Regras de benefícios condicionadas ao plano.

**Estado da integração:** as rotas de assinatura presentes nesta versão ativam ou alteram planos em modo simulado. O webhook existente não implementa validação criptográfica do provedor e não deve ser utilizado para confirmar pagamentos reais. Mercado Pago e Stripe não estão integrados de ponta a ponta no código analisado.

### Recursos sociais

- Busca de usuários.
- Solicitações de amizade, aceite, recusa e remoção.
- Favoritos.
- Criação e gerenciamento básico de grupos.
- Membros e configurações de grupos.
- Conversas de grupo e páginas de mensagens diretas.

O pacote Flask-SocketIO consta nas dependências, mas a versão analisada não contém inicialização de Socket.IO nem handlers de eventos. Portanto, não se deve descrever as conversas atuais como comunicação em tempo real via WebSocket.

### Competições

- Listagem e detalhes de competições/torneios.
- Entrada em torneios.
- Registro de respostas.
- Encerramento e processamento de resultados.
- Recompensas associadas às posições, conforme a implementação existente.
- Criação administrativa de torneios.

### Painel administrativo

- Visão geral administrativa.
- Criação, edição e exclusão de matérias.
- Criação, edição e exclusão de questões.
- Listagem e gerenciamento de usuários.
- Ação administrativa de banimento.
- Visualização de registros de auditoria.
- Criação de competições.

As rotas administrativas verificam a condição de administrador no backend. Não confie apenas na ocultação de links ou botões no frontend como mecanismo de autorização.

---

## Tecnologias

| Camada | Tecnologias presentes |
|---|---|
| Linguagem | Python |
| Backend web | Flask 3 |
| Templates | Jinja2 / HTML |
| Frontend | CSS e JavaScript |
| ORM | Flask-SQLAlchemy / SQLAlchemy 2 |
| Banco local padrão | SQLite |
| Migrações | Flask-Migrate / Alembic |
| Autenticação de sessão | Flask-Login |
| Hash de senha | Flask-Bcrypt |
| Proteção CSRF | Flask-WTF |
| E-mail | Flask-Mail |
| Configuração local | python-dotenv |
| Sanitização | Bleach |
| Imagens | Pillow e validação de arquivos no módulo de segurança |
| Fórmulas matemáticas | KaTeX local |

As versões diretas e transitivas das dependências estão registradas em [`requirements.txt`](requirements.txt). O arquivo deve ser a referência para a instalação do ambiente Python.

---

## Arquitetura atual

O projeto segue uma estrutura Flask baseada em application factory e um Blueprint principal.

- `main.py` cria a aplicação por meio de `create_app()` e inicia o servidor de desenvolvimento.
- `app/__init__.py` configura extensões, banco, segurança básica, contexto dos templates, criação inicial das tabelas e carga inicial da loja.
- `app/views.py` concentra as rotas HTTP e boa parte dos fluxos de negócio.
- `app/models.py` define entidades e relacionamentos persistidos pelo SQLAlchemy.
- `app/forms.py` define formulários e validações WTForms.
- `app/security.py` contém sanitização, validação de texto, validação de imagens, geração de nomes de arquivo e registro de auditoria.
- `app/templates/` contém as páginas Jinja.
- `app/static/` contém CSS, JavaScript, imagens, uploads e bibliotecas frontend locais.
- `migrations/` contém o histórico Alembic.

### Diagrama simplificado

```text
Navegador
   |
   | HTTP / formulários
   v
Flask (main.py / create_app)
   |
   +-- Blueprint main (app/views.py)
   |      +-- Autenticação e perfil
   |      +-- Questões e simulados
   |      +-- Progressão e ranking
   |      +-- Loja e Premium
   |      +-- Social e competições
   |      +-- Administração
   |
   +-- WTForms / Flask-WTF
   +-- Flask-Login / Flask-Bcrypt
   +-- Flask-Mail
   +-- Flask-SQLAlchemy
             |
             v
        SQLite local
        (instance/database.db)
```

A arquitetura descrita é a arquitetura existente no snapshot, não uma declaração de que a aplicação já está modularizada em serviços independentes. Em particular, `app/views.py` concentra um número elevado de rotas e regras de negócio e é um candidato prioritário a refatoração incremental.

## Estrutura do repositório

```text
ExQuest/
├── app/
│   ├── __init__.py
│   ├── forms.py
│   ├── models.py
│   ├── security.py
│   ├── views.py
│   ├── templates/
│   │   ├── admin/
│   │   ├── competicoes/
│   │   ├── errors/
│   │   ├── loja/
│   │   ├── premium/
│   │   ├── questoes/
│   │   ├── social/
│   │   └── páginas principais (login, dashboard, perfil, ranking etc.)
│   └── static/
│       ├── css/
│       ├── js/
│       ├── img/       # recursos visuais oficiais
│       ├── data/      # diretórios de dados e uploads em runtime
│       └── vendor/
│           └── katex/ # biblioteca matemática local
├── instance/
│   └── database.db   # banco SQLite local; não versionar
├── migrations/
│   ├── env.py
│   └── versions/
├── docs/
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

Os diretórios e arquivos podem evoluir. Consulte o repositório para a estrutura efetiva da sua revisão.

---

## Domínio e dados

Os principais modelos identificados em `app/models.py` são:

| Modelo | Responsabilidade geral |
|---|---|
| `Usuario` | Conta, perfil, progresso, moedas e estado Premium |
| `Streak` | Sequência de atividade |
| `Materia` | Matérias/categorias de estudo |
| `Questao` | Enunciados, dificuldade, tipo e gabarito |
| `Alternativa` | Alternativas das questões objetivas |
| `RespostaUsuario` | Respostas registradas por usuário |
| `QuestaoRespondidaSessao` | Associação de respostas a sessões |
| `RecompensaNivelConcedida` | Controle de recompensas por nível |
| `ItemLoja` | Catálogo de itens virtuais |
| `InventarioItem` | Itens pertencentes ao usuário |
| `Amizade` | Relações e solicitações de amizade |
| `GrupoChat` / `GrupoMembro` | Grupos e participação de usuários |
| `GrupoConfig` | Preferências/configurações de grupos |
| `Mensagem` | Mensagens sociais armazenadas |
| `Torneio` | Dados das competições |
| `TorneioParticipante` | Participação em torneios |
| `TorneioResposta` | Respostas submetidas em torneios |
| `Assinatura` | Registros de assinatura Premium |
| `PagamentoHistorico` | Histórico de eventos financeiros exibidos ao usuário |
| `CompraMoedas` | Solicitações de compra de pacotes de moedas |
| `OfertaTrial` | Controle de oferta de período experimental |
| `AdsCredit` | Créditos relacionados ao fluxo de anúncios |
| `LogAuditoria` | Registro de operações relevantes |
| `ConteudoBloqueado` | Registros associados à moderação/bloqueio de conteúdo |
| `TokenRecuperacao` | Tokens de recuperação de conta |

A tabela acima resume responsabilidades pelo nome e pelo código dos modelos; não substitui a definição de colunas, constraints e relacionamentos no arquivo `app/models.py`.

## Rotas principais

As rotas abaixo são uma referência funcional resumida. A lista completa e atualizada está nos decoradores de `app/views.py`.

| Área | Caminhos principais |
|---|---|
| Autenticação | `/registro`, `/login`, `/logout`, `/recuperar-senha`, `/redefinir-senha/<token>` |
| Google OAuth | `/auth/google`, `/auth/google/callback` |
| Dashboard | `/`, `/dashboard` |
| Perfil | `/perfil/<username>`, `/perfil/editar`, `/perfil/senha`, `/perfil/pagamentos` |
| Questões | `/questoes` |
| Simulados | `/simulado`, `/simulado/iniciar` |
| Respostas | `/api/responder`, `/api/responder-discursiva` |
| Ranking | `/ranking` |
| Loja | `/loja`, `/loja/comprar/<item_id>`, `/inventario` |
| Moedas | `/loja/moedas`, `/loja/moedas/comprar/<pacote_id>` |
| Premium | `/premium`, `/premium/assinar/<plano>/<ciclo>`, `/premium/cancelar`, `/premium/reativar`, `/premium/trocar/<plano>/<ciclo>` |
| Social | `/social`, `/social/buscar`, `/social/grupo/...`, `/social/dm/<uid>` |
| Competições | `/competicoes`, `/competicoes/<torneio_id>` |
| Administração | `/admin`, `/admin/materias`, `/admin/questoes`, `/admin/usuarios`, `/admin/logs`, `/admin/competicoes/novo` |

---

## Configuração e execução local

O passo a passo detalhado para Windows, Linux/macOS, e-mail, Google OAuth, banco de dados, administração e solução de problemas está em [`docs/GUIA_DE_INSTALACAO_E_DESENVOLVIMENTO.md`](docs/GUIA_DE_INSTALACAO_E_DESENVOLVIMENTO.md).

### Pré-requisitos

- Python instalado e disponível no terminal.
- Git, caso o projeto seja obtido por clone.
- Terminal com permissão para criar e ativar um ambiente virtual.

### Inicialização rápida no Windows (PowerShell)

```powershell
# Na pasta raiz do projeto
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Se o PowerShell bloquear `Activate.ps1`, execute uma vez para o usuário atual:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Abra `http://127.0.0.1:5000` no navegador.

### Inicialização rápida no Linux/macOS

```bash
cd ExQuest
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

O comando `python main.py` inicia o servidor embutido do Flask com `debug=True` no snapshot analisado. Utilize-o somente no desenvolvimento local, nunca como servidor de produção.

---

## Variáveis de ambiente

O carregamento do `.env` é feito por `python-dotenv`. As variáveis efetivamente lidas pelo código analisado são:

| Variável | Finalidade | Comportamento atual |
|---|---|---|
| `SECRET_KEY` | Assinatura de sessão e tokens Flask | O código possui fallback inseguro `dev-secret`; defina um valor forte em qualquer ambiente persistente e torne-o obrigatório em produção. |
| `DATABASE_URL` | URI SQLAlchemy do banco | Se ausente, usa `instance/database.db` (SQLite). |
| `MAIL_SERVER` | Servidor SMTP | Padrão: `smtp.gmail.com`. |
| `MAIL_PORT` | Porta SMTP | Padrão: `587`. |
| `MAIL_USE_TLS` | TLS SMTP | Padrão: `True`. |
| `MAIL_USERNAME` | Usuário SMTP/remetente | Padrão vazio. |
| `MAIL_PASSWORD` | Senha ou senha de aplicativo SMTP | Padrão vazio. |
| `GOOGLE_CLIENT_ID` | OAuth Google | Lida pelas rotas OAuth. |
| `GOOGLE_CLIENT_SECRET` | OAuth Google | Lida pelas rotas OAuth. |

Exemplo inicial de `.env` (substitua os valores localmente; nunca publique credenciais):

```dotenv
SECRET_KEY=gere-uma-chave-aleatoria-forte
# DATABASE_URL=sqlite:///instance/database.db

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=
MAIL_PASSWORD=

# Login Google: opcional
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

Gere uma chave Flask forte com:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

As variáveis `OPENAI_API_KEY`, `MP_ACCESS_TOKEN` e variáveis Stripe que possam existir em arquivos locais ou em versões antigas do tutorial **não são utilizadas pelos fluxos executáveis identificados nesta versão**. Não configure uma integração como pronta apenas por existir uma variável no `.env`.

---

## Banco de dados e migrations

### Banco local padrão

Sem `DATABASE_URL`, a aplicação usa:

```text
instance/database.db
```

O diretório `instance/` contém dados específicos do ambiente e não deve ser enviado ao GitHub. Preserve o banco local antes de qualquer refatoração ou atualização estrutural.

### Inicialização atual

Durante `create_app()`, o código executa `db.create_all()`, chama `_safe_add_columns()` e semeia o catálogo inicial da loja caso esteja vazio. Isso explica por que uma instalação local pode criar tabelas ao iniciar a aplicação.

### Migrations

O projeto contém Flask-Migrate/Alembic em `migrations/`. Entretanto, o snapshot analisado apresenta arquivos de migration duplicados com os mesmos identificadores de revisão e nomes com codificação diferente. Antes de executar `flask db upgrade`, criar novas migrations ou alterar o banco existente, audite e resolva esse histórico.

**Não execute** `flask db init` **sobre este repositório como etapa de instalação. Não apague nem recrie** `instance/database.db` **para contornar erros.** Faça backup e teste qualquer migration em uma cópia do banco.

---

## Arquivos enviados e assets

A aplicação salva uploads em subpastas de `app/static/data/`. Os caminhos identificados incluem:

| Diretório | Uso |
|---|---|
| `icon/` | Avatares enviados |
| `banner/` | Banners de perfil |
| `img_questao/` | Imagens anexadas às questões |
| `chat_files/` | Arquivos enviados em conversas |
| `chat_imgs/` | Imagens enviadas em conversas |
| `loja/` | Recursos de itens da loja |
| `bordas/` | Recursos de bordas |
| `efeitos/` | Recursos de efeitos |
| `badges_loja/` | Badges da loja |
| `badges/` | Imagens oficiais de badges Premium incluídas no projeto |

Uploads de usuários, bancos locais, logs e backups não devem ser versionados. Mantenha no repositório somente assets oficiais necessários para uma instalação limpa. Consulte `.gitignore` antes de adicionar novos arquivos.

### KaTeX

`app/static/vendor/katex/` contém a biblioteca KaTeX utilizada para renderizar expressões matemáticas. O CSS, JavaScript, script de auto-render e fontes são servidos localmente pelo template base. Essa pasta é uma dependência de runtime e deve permanecer versionada, juntamente com os avisos de licença correspondentes.

---

## Segurança e privacidade

O código atual contém mecanismos como:

- Hash de senhas com Flask-Bcrypt.
- Gerenciamento de sessão com Flask-Login.
- Proteção CSRF com Flask-WTF.
- Sanitização de texto com Bleach.
- Validação de username e de alguns campos textuais.
- Validação de imagens por extensão, assinatura de arquivo e tamanho.
- Limite global de upload configurado no Flask.
- Cabeçalhos HTTP de segurança definidos em `after_request`.
- Verificação de acesso administrativo nas rotas protegidas.
- Registros de auditoria para operações selecionadas.

Essas medidas não equivalem a uma auditoria de segurança completa. O filtro de termos banidos é básico e baseado em correspondência textual; não é um sistema abrangente de moderação contextual.

### Requisitos antes de produção

Antes de disponibilizar a aplicação publicamente:

1. Remova o fallback `dev-secret` e exija `SECRET_KEY` forte.
2. Desative o modo debug e utilize um servidor WSGI adequado.
3. Configure cookies `Secure` quando toda a aplicação estiver sob HTTPS.
4. Revise a política de proxy, HSTS e Content Security Policy para o domínio e os recursos realmente utilizados.
5. Corrija e teste o histórico Alembic.
6. Implemente gateways e webhooks com assinatura verificada, idempotência, validação de valor/usuário/produto e conciliação antes de aceitar pagamentos reais.
7. Revise autorização por objeto, uploads, rate limiting e exposição de dados pessoais.
8. Configure backup, restauração, monitoramento e retenção de logs.
9. Teste os fluxos críticos com dados não reais antes do lançamento.

---

## Integrações e limitações conhecidas

Esta seção evita confundir uma tela existente com uma integração funcional.

| Recurso | Situação no código analisado |
|---|---|
| SQLite / SQLAlchemy | Implementado para uso local. |
| SMTP / recuperação de senha | Configuração presente; depende de credenciais SMTP válidas e testes de entrega. |
| Google OAuth | Rotas presentes; depende de credenciais e da dependência Authlib, que não aparece fixada no `requirements.txt` analisado. |
| Avaliação discursiva por LLM/OpenAI | Não identificada. A avaliação atual é heurística e local. |
| Mercado Pago | Não implementado de ponta a ponta. |
| Stripe | Não implementado de ponta a ponta. |
| Compra real de pacotes de moedas | Fluxo cria registro pendente e contém TODO para gateway; não cobra nem credita após confirmação real. |
| Assinaturas Premium pagas | Rotas em modo simulado; não utilizar para cobrança real. |
| Webhooks financeiros | Não possuem validação suficiente para confiar em notificações externas nesta versão. |
| Anúncios de terceiros | O fluxo visual/créditos interno não configura uma rede de anúncios real. |
| Chat em tempo real via Socket.IO | Não há handlers Socket.IO identificados nesta versão. |
| SEO avançado / sitemap | Não presumir implementação completa; auditar antes de divulgar como recurso pronto. |

---

## Administração

O painel administrativo fica sob `/admin`. O acesso é restrito a contas com `is_admin=True`.

Para promover uma conta em ambiente local de desenvolvimento, abra um shell Flask:

```bash
flask --app main shell
```

Então execute:

```python
from app import db
from app.models import Usuario

usuario = Usuario.query.filter_by(email="seu-email@example.com").first()
if usuario is None:
    raise RuntimeError("Usuário não encontrado")

usuario.is_admin = True
db.session.commit()
```

Faça isso somente em um ambiente controlado e nunca exponha essa operação como endpoint público. Confirme a identidade do usuário e mantenha o acesso administrativo limitado.

---

## Testes e qualidade

O snapshot fornecido não contém uma suíte automatizada de testes (por exemplo, diretório `tests/` ou configuração pytest). Portanto, não há cobertura automatizada documentada nesta revisão.

Ao desenvolver novas funcionalidades, adicione testes para:

- Autenticação, recuperação de senha e permissões.
- Isolamento dos dados entre usuários.
- CRUD administrativo.
- Respostas e recompensas de questões.
- Compras internas, saldo e inventário.
- Concorrência e operações duplicadas.
- Ciclo de vida Premium.
- Uploads e validação de arquivos.
- Participação, respostas e finalização de competições.
- Migrations em cópias reais do banco.

Não considere uma funcionalidade validada apenas porque a página abre ou o botão responde.

---

## Execução em produção

O repositório analisado ainda requer ajustes antes de ser considerado pronto para produção. Em particular, `main.py` inicia o servidor Flask com `debug=True`, a chave secreta possui fallback de desenvolvimento e as rotas financeiras são simuladas/incompletas.

Uma implantação responsável deve utilizar:

- Configuração separada para desenvolvimento, teste e produção.
- Servidor WSGI apropriado e dependências fixadas para deploy.
- HTTPS terminado em proxy/reverse proxy confiável.
- Banco de dados gerenciado e backup testado, se necessário para a escala do produto.
- Armazenamento persistente para uploads ou serviço de objetos.
- Segredos armazenados no ambiente do provedor, não no repositório.
- Logs estruturados, monitoramento e health checks.
- Processo de deploy e rollback documentado.

Não utilize `python main.py` como comando de produção.

---

## Documentação complementar

- [Guia de instalação e desenvolvimento](docs/Guia_Instalacao_Desenvolvimento_ExQuest.md) — criação do ambiente, `.env`, execução, SMTP, Google OAuth, banco e solução de problemas.
- [Código dos modelos](app/models.py) — definição detalhada das entidades e relacionamentos.
- [Rotas da aplicação](app/views.py) — endpoints e fluxos HTTP.
- [Formulários](app/forms.py) — formulários e validações WTForms.
- [Módulo de segurança](app/security.py) — sanitização e validação de dados/arquivos.
- [Dependências](requirements.txt) — pacotes Python.

## Licença e propriedade intelectual

Consulte o arquivo [`LICENSE`](LICENSE) na raiz do repositório para conhecer os termos aplicáveis ao código original do ExQuest.

Bibliotecas, fontes, ícones e demais componentes de terceiros permanecem sujeitos às respectivas licenças e avisos de copyright. A licença do ExQuest não substitui nem altera essas condições.
