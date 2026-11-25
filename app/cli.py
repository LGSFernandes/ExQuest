import click
from flask_migrate import upgrade

from app.services import backup


def register_cli(app) -> None:
    @app.cli.command("backup")
    def backup_cmd():
        """Cria um backup consistente do banco SQLite em instance/backups/."""
        destino = backup.backup_sqlite("manual")
        if destino is None:
            raise click.ClickException("Backup automático só para SQLite. Em PostgreSQL use pg_dump (veja a documentação).")
        click.echo(f"Backup criado: {destino}")

    @app.cli.command("loja-seed")
    def loja_seed_cmd():
        """Cria os itens do catálogo que ainda não existem (não altera preço nem itens já cadastrados)."""
        from app.extensions import db
        from app.services import catalogo
        criados, existentes = catalogo.semear()
        db.session.commit()
        click.echo(f"Catálogo: {criados} criado(s), {existentes} já existia(m).")

    @app.cli.command("competicoes-encerrar")
    def competicoes_encerrar_cmd():
        """Encerra competições vencidas e paga os prêmios (seguro rodar de tempos em tempos)."""
        from app.extensions import db
        from app.services import competicoes
        n = competicoes.encerrar_vencidos()
        db.session.commit()
        click.echo(f"Competições encerradas: {n}.")

    @app.cli.command("premium-expirar")
    def premium_expirar_cmd():
        """Remove o Premium vencido (rode a cada hora via cron/agendador)."""
        from app.extensions import db
        from app.services import premium
        n = premium.expirar_vencidos()
        db.session.commit()
        click.echo(f"Premium expirado em {n} conta(s).")

    @app.cli.command("pagamentos-reconciliar")
    @click.option("--minutos", default=15, show_default=True, help="Só pedidos pendentes criados há mais que isso.")
    def pagamentos_reconciliar_cmd(minutos):
        """Consulta o provedor dos pedidos pendentes (cobre webhook perdido). Rode a cada 15 min."""
        from datetime import timedelta
        from sqlalchemy import select
        from app import clock
        from app.extensions import db
        from app.models import Pagamento
        from app.services import pagamentos
        limite = clock.agora() - timedelta(minutes=minutos)
        pend = db.session.scalars(select(Pagamento).where(Pagamento.status.in_(("criado", "pendente")),
                                                          Pagamento.criado_em <= limite)).all()
        mudou = 0
        for pg in pend:
            try:
                antes = pg.status
                pagamentos.reconciliar(pg)
                db.session.commit()
                mudou += pg.status != antes
            except Exception as exc:  # um provedor fora do ar não pode travar os demais
                db.session.rollback()
                click.echo(f"pedido {pg.id}: {exc}", err=True)
        click.echo(f"{len(pend)} pedido(s) consultado(s), {mudou} atualizado(s).")

    @app.cli.command("manutencao")
    @click.pass_context
    def manutencao_cmd(ctx):
        """Rotina periódica única (rode a cada 5 min): encerra competições, expira Premium, reconcilia pagamentos."""
        ctx.invoke(competicoes_encerrar_cmd)
        ctx.invoke(premium_expirar_cmd)
        ctx.invoke(pagamentos_reconciliar_cmd, minutos=15)
        from flask import current_app
        from app.services import jobs, rum
        click.echo(f"Métricas RUM antigas removidas: {rum.limpar_antigos(current_app.config['RUM_RETENCAO_DIAS'])}; jobs concluídos removidos: {jobs.limpar_antigos()}.")

    @app.cli.command("imagens-otimizar")
    @click.option("--aplicar", is_flag=True, help="Sem esta opção só mostra o que mudaria (nada é gravado).")
    def imagens_otimizar_cmd(aplicar):
        """Converte uploads antigos (PNG/JPEG) para WebP reduzido e atualiza o banco. O original só é apagado depois do commit."""
        from sqlalchemy import select
        from app.extensions import db
        from app.models import Mensagem, Questao, Usuario
        from app.services import uploads
        alvos = [(Usuario, "icon_path", "icon", False), (Usuario, "banner_path", "banner", False),
                 (Questao, "imagem_path", "img_questao", False), (Mensagem, "imagem_path", "chat", True)]
        total = economia = 0
        for modelo, col, pasta, privado in alvos:
            for obj in db.session.scalars(select(modelo).where(getattr(modelo, col).is_not(None))):
                antigo = getattr(obj, col)
                novo = uploads.reotimizar(pasta, antigo, privado=privado)
                if not novo:
                    continue
                a, n = uploads.caminho(pasta, antigo, privado=privado), uploads.caminho(pasta, novo, privado=privado)
                economia += a.stat().st_size - n.stat().st_size
                total += 1
                if aplicar:
                    setattr(obj, col, novo)
                    db.session.commit()  # o banco já aponta para o novo arquivo; só então apagamos o velho
                    uploads.remover(pasta, antigo, privado=privado)
                else:
                    n.unlink()
        click.echo(f"{total} imagem(ns) {'convertida(s)' if aplicar else 'seriam convertidas'}; economia de {economia / 1024:.0f} KB.")

    @app.cli.command("jobs-worker")
    @click.option("--uma-vez", is_flag=True, help="Executa o que estiver pendente e sai (útil em cron/testes).")
    @click.option("--intervalo", default=2.0, show_default=True, help="Segundos entre consultas à fila.")
    def jobs_worker_cmd(uma_vez, intervalo):
        """Executa os jobs da fila (e-mails etc.). Em produção: um ou mais processos com JOBS_MODE=queue no app."""
        import signal
        import time
        from app.extensions import db
        from app.services import jobs
        parar = {"v": False}
        signal.signal(signal.SIGTERM, lambda *_: parar.update(v=True))
        signal.signal(signal.SIGINT, lambda *_: parar.update(v=True))
        ultimo_limpeza = 0.0
        while not parar["v"]:
            try:
                r = jobs.executar_pendentes()
                if any(r.values()):
                    click.echo(f"jobs: {r}")
                if time.monotonic() - ultimo_limpeza > 3600:
                    jobs.limpar_antigos()
                    ultimo_limpeza = time.monotonic()
            except Exception as exc:  # noqa: BLE001 - o worker não morre por erro de banco momentâneo
                db.session.rollback()
                click.echo(f"worker: {type(exc).__name__}: {exc}", err=True)
            if uma_vez:
                break
            time.sleep(intervalo)

    @app.cli.command("promover-admin")
    @click.argument("email")
    def promover_admin_cmd(email):
        """Dá acesso de administrador a uma conta existente."""
        from app.extensions import db
        from app.models import Usuario
        u = Usuario.query.filter_by(email=email.strip().lower()).first()
        if u is None:
            raise click.ClickException("Nenhuma conta com esse e-mail.")
        u.is_admin = True
        db.session.commit()
        click.echo(f"{u.email} agora é administrador.")

    @app.cli.command("conceder-premium")
    @click.argument("email")
    @click.option("--plano", type=click.Choice(["basic", "inter", "advan"]), default="advan", show_default=True)
    @click.option("--dias", type=click.IntRange(1, 3650), default=365, show_default=True)
    def conceder_premium_cmd(email, plano, dias):
        """Concede Premium sem pagamento (cortesia/teste). Fica registrado na auditoria e na assinatura como 'manual'."""
        from datetime import timedelta
        from app import clock
        from app.extensions import db
        from app.models import Assinatura, Usuario
        from app.services import audit
        u = Usuario.query.filter_by(email=email.strip().lower()).first()
        if u is None:
            raise click.ClickException("Nenhuma conta com esse e-mail.")
        agora = clock.agora()
        for a in Assinatura.query.filter_by(usuario_id=u.id, status="ativa"):
            a.status, a.atualizado_em = "substituida", agora
        u.plano_premium, u.premium_ciclo, u.premium_expira = plano, "mensal", agora + timedelta(days=dias)
        u.premium_cancelar_em = None
        db.session.add(Assinatura(usuario_id=u.id, plano=plano, ciclo="mensal", status="ativa", inicio=agora, expira=u.premium_expira,
                                  renovacao_auto=False, provider="manual", provider_assinatura_id="cli"))
        audit.registrar("premium_concedido_cli", u.id, f"{plano} {dias}d")
        db.session.commit()
        click.echo(f"{u.email}: plano {plano} até {u.premium_expira:%d/%m/%Y}.")

    @app.cli.command("migrar")
    def migrar_cmd():
        """Migração segura: backup -> flask db upgrade -> verificação de integridade."""
        destino = backup.backup_sqlite("pre_migracao")
        if destino:
            click.echo(f"Backup pré-migração: {destino}")
        elif backup.caminho_sqlite() is None:
            click.echo("Banco não é SQLite: faça o backup com pg_dump antes de continuar.", err=True)
        else:
            click.echo("Banco ainda não existe: será criado do zero (sem backup necessário).")
        try:
            upgrade()
        except Exception as exc:
            if destino:
                click.echo(f"\nA migração falhou. Para restaurar o estado anterior, pare o app e copie:\n  {destino}  ->  {backup.caminho_sqlite()}", err=True)
            raise click.ClickException(f"Falha na migração: {exc}")
        problemas = backup.verificar_integridade_sqlite()
        if problemas:
            raise click.ClickException("Integridade comprometida após a migração: " + "; ".join(problemas[:5]))
        click.echo("Migração concluída e banco íntegro.")
