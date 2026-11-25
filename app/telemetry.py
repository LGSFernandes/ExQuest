"""Observabilidade de desempenho.

1) Log de requisição lenta (sempre ligado, sem dependências): rota, método, status, tempo total, nº e tempo de consultas SQL.
   Não registra URL com query string nem corpo (podem ter dados pessoais).
2) OpenTelemetry (opcional): OTEL_ENABLED=true + OTEL_EXPORTER_OTLP_ENDPOINT + `pip install -r requirements-otel.txt`.
   Instrumenta Flask, SQLAlchemy e requests (APIs externas) e exporta spans por OTLP/HTTP.
"""
import logging
import time

from flask import g, has_request_context, request
from sqlalchemy import event

log = logging.getLogger("exquest.lento")


def init_app(app) -> None:
    from app.extensions import db

    with app.app_context():
        engine = db.engine

    @event.listens_for(engine, "before_cursor_execute")
    def _antes(conn, cur, stmt, params, ctx, many):
        ctx._t0 = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _depois(conn, cur, stmt, params, ctx, many):
        if has_request_context():  # CLI e worker não têm requisição
            g.db_n = getattr(g, "db_n", 0) + 1
            g.db_s = getattr(g, "db_s", 0.0) + (time.perf_counter() - ctx._t0)

    @app.before_request
    def _inicio():
        g.t0 = time.perf_counter()

    @app.after_request
    def _fim(resp):
        t0 = getattr(g, "t0", None)
        if t0 is not None and request.endpoint != "static":
            ms = (time.perf_counter() - t0) * 1000
            if ms >= app.config["SLOW_REQUEST_MS"]:
                log.warning("requisição lenta: %s %s -> %s em %.0f ms (%d consultas, %.0f ms de banco)", request.method,
                            request.endpoint, resp.status_code, ms, getattr(g, "db_n", 0), getattr(g, "db_s", 0.0) * 1000)
        return resp

    if app.config.get("OTEL_ENABLED"):
        _iniciar_otel(app, engine)


def _iniciar_otel(app, engine) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.error("OTEL_ENABLED=true, mas os pacotes não estão instalados (pip install -r requirements-otel.txt)")
        return
    provider = app.extensions.get("otel_provider")
    if provider is None:
        provider = TracerProvider(resource=Resource.create({"service.name": app.config.get("OTEL_SERVICE_NAME", "exquest")}))
        if app.config.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # lê OTEL_EXPORTER_OTLP_ENDPOINT do ambiente
        trace.set_tracer_provider(provider)
        app.extensions["otel_provider"] = provider
    FlaskInstrumentor().instrument_app(app, tracer_provider=provider, excluded_urls="static,healthz")
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider, enable_commenter=False)
    RequestsInstrumentor().instrument(tracer_provider=provider)
