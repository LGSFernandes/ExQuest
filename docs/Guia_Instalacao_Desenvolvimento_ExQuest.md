# Guia de instalação e desenvolvimento — ExQuest

Este documento preserva a finalidade prática do README anterior: orientar a configuração do ambiente local, das variáveis do `.env` e dos serviços efetivamente reconhecidos pelo código analisado.

> **Importante:** este guia foi escrito com base no snapshot atual do repositório. O código contém integrações simuladas e pendências descritas em [Integrações não implementadas](#integrações-não-implementadas). Não use as rotas de pagamento atuais para receber dinheiro real.

## 1. Pré-requisitos

- Python instalado e disponível no terminal.
- Git (opcional, caso utilize clone).
- Acesso de escrita à pasta do projeto.
- Uma conta SMTP, somente se desejar testar envio de e-mails.
- Um projeto OAuth no Google Cloud, somente se desejar habilitar login Google.

Recomenda-se utilizar uma versão estável do Python compatível com todos os pacotes fixados em `requirements.txt`. Caso haja falha de instalação em uma versão muito recente do Python, utilize uma versão suportada pelas dependências do projeto.

## 2. Preparar o ambiente no Windows

Abra PowerShell na pasta raiz do projeto:

```powershell
cd C:\Users\SEU_USUARIO\Documents\ExQuest
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Erro de política de execução do PowerShell

Se o PowerShell bloquear `Activate.ps1`, configure a política para o usuário atual:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Confirme com `S` quando solicitado, feche o terminal, abra novamente e ative o ambiente:

```powershell
.\.venv\Scripts\Activate.ps1
```

Verifique:

```powershell
Get-ExecutionPolicy -List
```

A configuração esperada em `CurrentUser` é `RemoteSigned`. Não é necessário desativar globalmente a política de execução.

## 3. Preparar o ambiente no Linux/macOS

```bash
cd ExQuest
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Criar e configurar o `.env`

Crie um arquivo chamado `.env` na raiz do projeto. Não envie esse arquivo ao GitHub e não compartilhe capturas de tela que mostrem os valores.

Modelo para a versão analisada:

```dotenv
# Obrigatória para sessões seguras em ambientes persistentes
SECRET_KEY=

# Opcional: se omitida, a aplicação usa SQLite em instance/database.db
# DATABASE_URL=sqlite:///instance/database.db

# SMTP — recuperação de senha e envio de e-mails
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=
MAIL_PASSWORD=

# Google OAuth — opcional
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

Gere `SECRET_KEY` com:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copie o resultado para `SECRET_KEY`. Não reutilize uma chave publicada em logs, screenshots, mensagens ou repositórios.

### Variáveis que o código atual realmente lê

| Nome | Obrigatória? | Onde é utilizada |
|---|---:|---|
| `SECRET_KEY` | Sim para qualquer ambiente persistente; atualmente existe fallback inseguro | Configuração Flask |
| `DATABASE_URL` | Não, se utilizar SQLite local | SQLAlchemy |
| `MAIL_SERVER` | Não, mas necessário para SMTP | Flask-Mail |
| `MAIL_PORT` | Não, mas necessário para SMTP | Flask-Mail |
| `MAIL_USE_TLS` | Não, mas necessário para SMTP | Flask-Mail |
| `MAIL_USERNAME` | Não, mas necessário para SMTP | Flask-Mail/remetente |
| `MAIL_PASSWORD` | Não, mas necessário para SMTP | Flask-Mail |
| `GOOGLE_CLIENT_ID` | Não, somente OAuth Google | Rotas `/auth/google` |
| `GOOGLE_CLIENT_SECRET` | Não, somente OAuth Google | Rotas `/auth/google/callback` |

`FLASK_ENV` e `FLASK_DEBUG` podem existir em arquivos `.env` antigos, mas o `main.py` analisado chama `app.run(debug=True)` diretamente. Portanto, essas variáveis não desativam o modo debug desse arquivo.

## 5. Configurar SMTP para recuperação de senha

O projeto utiliza Flask-Mail. Sem credenciais SMTP válidas, o envio de e-mails de recuperação de senha não estará disponível.

### Exemplo com Gmail

1. Acesse [Conta Google](https://myaccount.google.com/).
2. Abra a área de segurança da conta.
3. Ative a verificação em duas etapas, caso ainda não esteja ativa.
4. Consulte a seção de senhas de app, se ela estiver disponível para sua conta.
5. Gere uma senha de aplicativo para o ExQuest.
6. Copie a senha gerada e utilize-a em `MAIL_PASSWORD` (remova espaços de apresentação, se houver).
7. Preencha o `.env`:

```dotenv
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=seu-email@gmail.com
MAIL_PASSWORD=senha-de-aplicativo
```

8. Reinicie o servidor para recarregar as variáveis.
9. Teste a recuperação de senha com uma conta de teste e confira também a caixa de spam.

A disponibilidade de senhas de aplicativo depende das políticas e configurações da conta Google. Para outros provedores, utilize os dados SMTP documentados pelo próprio provedor.

## 6. Configurar Google OAuth (opcional)

O código possui rotas `/auth/google` e `/auth/google/callback` e lê `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`.

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie ou selecione um projeto.
3. Configure a tela de consentimento OAuth conforme as exigências atuais do Google.
4. Abra a área de APIs e serviços / credenciais.
5. Crie um ID do cliente OAuth do tipo **Aplicativo da Web**.
6. Configure as origens JavaScript para o ambiente de desenvolvimento e o domínio de produção, quando aplicável.
7. Cadastre o URI de redirecionamento que corresponde ao endpoint gerado pela aplicação. Para desenvolvimento local, a rota é `http://127.0.0.1:5000/auth/google/callback` se a aplicação for acessada por esse host; `localhost` e `127.0.0.1` são origens distintas para fins de OAuth.
8. Copie o ID e o segredo para o `.env`:

```dotenv
GOOGLE_CLIENT_ID=seu-client-id
GOOGLE_CLIENT_SECRET=seu-client-secret
```

9. Reinicie a aplicação e teste o fluxo de login.

**Dependência pendente:** as rotas importam `authlib`, mas o `requirements.txt` fornecido não fixa Authlib. Antes de utilizar Google OAuth em uma instalação limpa, adicione uma versão compatível de `Authlib` às dependências do projeto e atualize `requirements.txt`.

Consulte sempre a documentação oficial do [Google Identity / OAuth](https://developers.google.com/identity) para requisitos atuais de consentimento, escopos e URLs autorizadas.

## 7. Banco de dados local

Por padrão, a aplicação utiliza SQLite em:

```text
instance/database.db
```

O diretório `instance/` é criado pela aplicação quando necessário. Se você já possui um banco local com dados de teste, faça uma cópia de segurança antes de atualizar o código.

O banco não deve ser incluído no repositório público. Em deploy, utilize armazenamento persistente e uma estratégia de backup compatível com o banco escolhido.

### Atenção às migrations existentes

O snapshot fornecido contém arquivos de migration duplicados com os mesmos IDs de revisão e nomes alternativos/acentuados. Além disso, `create_app()` executa `db.create_all()` e `_safe_add_columns()` durante a inicialização.

Por isso:

- Não execute `flask db init` como etapa de instalação.
- Não rode `flask db upgrade` no banco original antes de auditar e corrigir as duplicidades.
- Não apague `instance/database.db` para contornar erros.
- Faça backup e teste mudanças de esquema em uma cópia do banco.

A estratégia definitiva deve padronizar o uso de Alembic e remover alterações ad hoc do esquema após uma migração segura.

## 8. Executar o ExQuest

Com o ambiente virtual ativo e as dependências instaladas:

```bash
python main.py
```

Acesse:

```text
http://127.0.0.1:5000
```

**Somente desenvolvimento:** o `main.py` atual inicia o Flask com `debug=True`. Não utilize esse comando em produção.

## 9. Criar uma conta administradora em desenvolvimento

Crie uma conta normalmente pela interface. Em seguida, abra o shell Flask:

```bash
flask --app main shell
```

Execute:

```python
from app import db
from app.models import Usuario

usuario = Usuario.query.filter_by(email="seu-email@example.com").first()
if usuario is None:
    raise RuntimeError("Usuário não encontrado")

usuario.is_admin = True
db.session.commit()
```

Saia do shell com `exit()`. Não crie uma rota HTTP pública para promover usuários. Em produção, defina um procedimento administrativo controlado e auditável.

## 10. Uploads e arquivos estáticos

A aplicação armazena uploads locais sob `app/static/data/`, em pastas como:

- `icon/`: avatares.
- `banner/`: banners de perfil.
- `img_questao/`: imagens de questões.
- `chat_files/`: anexos de conversas.
- `chat_imgs/`: imagens de conversas.
- `loja/`, `bordas/`, `efeitos/`, `badges_loja/`: recursos da loja.

Esses arquivos são dados de runtime e não devem ser enviados ao GitHub. O ambiente deve manter esses diretórios graváveis. Para deploy com filesystem efêmero, configure volume persistente ou armazenamento externo e atualize a estratégia de URLs/armazenamento.

Assets oficiais como logos, favicons e badges que são necessários para a instalação devem permanecer versionados.

## 11. KaTeX e fórmulas matemáticas

A biblioteca KaTeX está em `app/static/vendor/katex/` e é carregada localmente pelo template base. Ela inclui:

- `katex.min.js`: motor de renderização.
- `katex.min.css`: estilos.
- `contrib/auto-render.min.js`: busca delimitadores e renderiza expressões.
- `fonts/`: fontes matemáticas usadas pelo CSS.

Não ignore essa pasta no `.gitignore` sem substituir a dependência e validar o funcionamento das fórmulas.

Delimitadores reconhecidos no template base incluem `$...$`, `$$...$$`, `\(...\)` e `\[...\]`.

## 12. Integrações não implementadas

O README antigo descrevia exemplos de integração manual com Mercado Pago e Stripe. Esses exemplos orientavam a substituir rotas diretamente no código e não correspondiam à implementação existente no repositório.

Na revisão analisada:

- `MP_ACCESS_TOKEN` não é lido pelos fluxos executáveis identificados.
- Não foi identificada integração Stripe executável.
- A rota de compra de pacotes de moedas registra uma compra pendente e contém um TODO para integração de gateway.
- O webhook de moedas aceita um payload JSON e altera o status/saldo sem validação criptográfica do provedor.
- A rota de Premium ativa planos em modo simulado.
- O webhook de Premium também não autentica a origem da notificação.
- `OPENAI_API_KEY` não é lida pelo avaliador de respostas discursivas; a avaliação atual é local e baseada em similaridade textual.

**Não cadastre credenciais de produção nem disponibilize os endpoints atuais como sistema de pagamentos reais.** A implementação futura deve incluir criação de checkout no provedor, verificação de assinatura do webhook, consulta do pagamento diretamente no provedor, conferência de usuário/valor/produto, idempotência, tratamento de reembolso e conciliação.

## 13. Problemas comuns

### PowerShell não permite ativar o ambiente virtual

Execute uma vez:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Porta 5000 já está em uso

Feche a aplicação que já utiliza a porta ou configure outra porta no comando de inicialização de desenvolvimento. Não inicie duas instâncias compartilhando o mesmo banco SQLite durante operações de alteração de esquema.

### Recuperação de senha não envia e-mail

Verifique `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME` e `MAIL_PASSWORD`. Confira as regras do provedor SMTP, autenticação em duas etapas, senha de aplicativo e spam.

### Login Google apresenta erro

Verifique `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, a URL de callback registrada no Google Cloud e a presença de Authlib no ambiente.

### Fórmulas aparecem sem formatação

Verifique se `app/static/vendor/katex/` está completo e se os arquivos CSS, JavaScript e fontes estão sendo servidos sem erro no navegador.

### Erro ao executar migrations

Não apague o banco. O histórico atual possui duplicidades de revisão. Faça backup, audite os arquivos em `migrations/versions/` e corrija o grafo Alembic antes de executar comandos de migration.

## 14. Checklist antes de compartilhar ou publicar

- [ ] `.env` não está sendo rastreado pelo Git.
- [ ] `instance/database.db` e backups estão ignorados.
- [ ] Uploads de usuários não estão sendo versionados.
- [ ] Assets oficiais necessários continuam versionados.
- [ ] `app/static/vendor/katex/` continua disponível.
- [ ] `requirements.txt` instala em ambiente virtual limpo.
- [ ] Dependências opcionais, como Authlib, estão documentadas e fixadas se utilizadas.
- [ ] Não há credenciais em logs, commits ou documentação.
- [ ] O modo debug está desativado antes de deploy.
- [ ] `SECRET_KEY` forte está configurada.
- [ ] Banco e migrations foram testados em cópia.
- [ ] Pagamentos não estão habilitados antes da implementação segura dos gateways.
