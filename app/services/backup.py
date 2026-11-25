"""Backup consistente do SQLite (API de backup do próprio SQLite: seguro mesmo com o app em uso)."""
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app

from app.extensions import db


def caminho_sqlite() -> Path | None:
    url = db.engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def backup_sqlite(sufixo: str = "manual") -> Path | None:
    origem = caminho_sqlite()
    if origem is None or not origem.exists():
        return None
    pasta = Path(current_app.instance_path) / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{origem.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{sufixo}.db"
    src = sqlite3.connect(origem.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destino)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return destino


def verificar_integridade_sqlite() -> list[str]:
    """Lista de problemas (vazia = íntegro)."""
    origem = caminho_sqlite()
    if origem is None:
        return []
    con = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    try:
        problemas = [r[0] for r in con.execute("PRAGMA integrity_check") if r[0] != "ok"]
        problemas += [f"FK violada: {tuple(r)}" for r in con.execute("PRAGMA foreign_key_check")]
        return problemas
    finally:
        con.close()
