def register_blueprints(app) -> None:
    """Cada blueprint é registrado aqui à medida que é migrado do antigo views.py."""
    from app.blueprints import admin, auth, colecoes, competicoes, missoes, notificacoes, social, loja, main, pagamentos, perfil, questoes, revisao, webhooks, ranking, simulados, rum
    from app.blueprints import chat  # noqa: F401  (rotas de mensagens: precisam entrar no blueprint "social" antes de ele ser registrado)
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    for m in (admin, colecoes, competicoes, missoes, notificacoes, social, questoes, simulados, ranking, loja, perfil, revisao, pagamentos, webhooks, rum):
        app.register_blueprint(m.bp)
    auth.init_google(app)
