"""Estáticos: URL versionada por conteúdo, CDN opcional, cache longo no navegador e compressão.

- `static_url('css/app.css')` -> `/static/css/app.css?v=<hash>` (ou `<CDN_URL>/static/...`). O hash muda quando o arquivo muda,
  então a URL pode ser cacheada por 1 ano (`immutable`) sem risco de servir versão velha.
- Uploads de usuário (`data/...`) têm nome aleatório e nunca são reescritos: também recebem cache longo, sem hash.
- Compressão Brotli/Gzip pelo Flask-Compress. HTML só é comprimido em GET sem query string (mitiga BREACH: o HTML leva o token CSRF
  e ecoa entradas do usuário nas buscas/validações).
"""
import hashlib
import json
import threading
from pathlib import Path
from urllib.parse import quote

from flask import current_app, request
from flask_compress import Compress

compress = Compress()
_hash_cache: dict[tuple[str, int, int], str] = {}
_lock = threading.Lock()
_ANO = 31536000


def _dist_manifest(app) -> dict:
    """tools/build_assets.py grava app/static/dist/manifest.json (nome-fonte -> nome minificado). Sem build, usa os fontes."""
    cache = app.extensions.setdefault("exq_manifest", {"mtime": None, "dados": {}})
    arq = Path(app.static_folder) / "dist" / "manifest.json"
    try:
        mt = arq.stat().st_mtime
    except OSError:
        cache.update(mtime=None, dados={})
        return cache["dados"]
    if cache["mtime"] != mt:
        try:
            cache.update(mtime=mt, dados=json.loads(arq.read_text("utf-8")))
        except (OSError, ValueError):
            cache.update(mtime=mt, dados={})
    return cache["dados"]


def _hash(app, rel: str) -> str | None:
    p = Path(app.static_folder) / rel
    try:
        st = p.stat()
    except OSError:
        return None
    chave = (rel, st.st_mtime_ns, st.st_size)
    with _lock:
        h = _hash_cache.get(chave)
        if h is None:
            h = hashlib.sha256(p.read_bytes()).hexdigest()[:10]
            if len(_hash_cache) > 500:
                _hash_cache.clear()
            _hash_cache[chave] = h
    return h


def static_url(filename: str) -> str:
    app = current_app
    filename = filename.lstrip("/")
    if app.config.get("USE_DIST", True) and not app.config.get("TESTING"):
        filename = _dist_manifest(app).get(filename, filename)
    base = app.config.get("CDN_URL") or ""
    caminho = f"{base}/static/{quote(filename)}" if base else f"{app.static_url_path}/{quote(filename)}"
    if filename.startswith("data/"):
        return caminho  # nome aleatório imutável
    h = _hash(app, filename)
    return f"{caminho}?v={h}" if h else caminho


def init_app(app) -> None:
    app.config.setdefault("COMPRESS_REGISTER", False)
    app.config["COMPRESS_REGISTER"] = False  # decidimos por requisição abaixo
    app.config.setdefault("COMPRESS_MIN_SIZE", 500)
    app.config.setdefault("COMPRESS_ALGORITHM_STREAMING", ["zstd", "br", "gzip"])  # arquivos estáticos chegam como stream; navegadores antigos só aceitam gzip
    compress.init_app(app)

    original = app.jinja_env.globals["url_for"]

    def url_for(endpoint, **values):
        if endpoint == "static" and "filename" in values and not values.get("_external"):
            return static_url(values["filename"])
        return original(endpoint, **values)

    app.jinja_env.globals["url_for"] = url_for

    @app.after_request
    def _cache_e_compressao(resp):
        if request.endpoint == "static" and resp.status_code == 200:
            rel = request.view_args.get("filename", "") if request.view_args else ""
            if "v" in request.args or rel.startswith("data/"):
                resp.headers["Cache-Control"] = f"public, max-age={_ANO}, immutable"
            elif rel.startswith(("fonts/", "vendor/")):
                resp.headers["Cache-Control"] = "public, max-age=2592000"
            else:
                resp.headers["Cache-Control"] = "public, max-age=86400"
            if app.config.get("CDN_URL"):
                resp.headers.setdefault("Access-Control-Allow-Origin", "*")  # fontes servidas pela CDN exigem CORS
        if resp.mimetype == "text/html" and (request.method != "GET" or request.query_string or not app.config.get("COMPRESS_HTML", True)):
            return resp
        return compress.after_request(resp)
