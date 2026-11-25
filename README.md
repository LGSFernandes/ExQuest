# ExQuest

Plataforma de estudos gamificada: questões comentadas (com LaTeX), simulados com tempo, revisão espaçada, coleções, missões, competições, ranking, loja de cosméticos, amigos e mensagens, e planos Premium.

Stack: Flask 3 (app factory + blueprints), SQLAlchemy 2 / Flask-Migrate, SQLite (PostgreSQL opcional), Flask-Login, CSRF, Flask-Limiter. Sem JavaScript ou estilo inline (CSP estrita); KaTeX e ícones Lucide são servidos localmente.

## Começar (desenvolvimento)

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                                  # ajuste ao menos BASE_URL e SECRET_KEY
flask --app main migrar                               # backup + migrations + verificação
flask --app main loja-seed                            # catálogo da loja (não altera itens existentes)
flask --app main promover-admin voce@exemplo.com      # depois de criar a conta pelo site
python main.py                                        # http://127.0.0.1:5000
```

Nunca use `flask db init` / `flask db migrate`: as migrations já existem em `migrations/`.

## Testes

```bash
python -m pytest -q
```

## Documentação

- [Guia de instalação e desenvolvimento](docs/GUIA_DE_INSTALACAO_E_DESENVOLVIMENTO.md): ambiente, comandos, produção, Docker, rotinas agendadas.
- [Tutorial de serviços externos](docs/TUTORIAL_SERVICOS_EXTERNOS.md): e-mail, Google, Mercado Pago, Stripe.
- [Segurança](docs/SEGURANCA.md) e [pendências do responsável](docs/PENDENCIAS_DO_RESPONSAVEL.md).
- [Decisões de arquitetura](docs/adr/) e [plano de execução](docs/PLANO_DE_EXECUCAO.md) (histórico, estado e limitações conhecidas).
