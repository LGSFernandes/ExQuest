"""Timeout único para todas as chamadas a APIs externas (conexão e leitura separados; config HTTP_CONNECT_TIMEOUT/HTTP_READ_TIMEOUT)."""
from flask import current_app


def timeout() -> tuple[float, float]:
    c = current_app.config
    return (c["HTTP_CONNECT_TIMEOUT"], c["HTTP_READ_TIMEOUT"])
