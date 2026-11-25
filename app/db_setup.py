"""Pragmas do SQLite: integridade referencial ligada, WAL e timeout de lock (vários workers)."""
import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine

_estado = {"wal": True, "instalado": False}


def _pragmas(dbapi_conn, _record):
    if not isinstance(dbapi_conn, sqlite3.Connection):
        return
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=8000")
    if _estado["wal"]:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def install_sqlite_pragmas(app) -> None:
    _estado["wal"] = bool(app.config.get("SQLITE_WAL", True))
    if not _estado["instalado"]:  # create_app pode rodar várias vezes (testes); registra uma só vez
        event.listen(Engine, "connect", _pragmas)
        _estado["instalado"] = True
