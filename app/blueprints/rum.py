"""Recebe as métricas de velocidade do navegador (navigator.sendBeacon). Sem login e sem CSRF (o beacon não envia cabeçalhos),
por isso tudo é validado, o tamanho é limitado e há limite de taxa por IP."""
import json

from flask import Blueprint, abort, current_app, request

from app.extensions import csrf, db, limiter
from app.services import rum

bp = Blueprint("rum", __name__)


@bp.post("/rum")
@csrf.exempt
@limiter.limit("30 per minute")
def receber():
    if not current_app.config["RUM_ENABLED"]:
        return "", 204
    bruto = request.get_data(cache=False)[:1025]  # teto de 1 KB mesmo sem Content-Length (corpo em pedaços)
    if len(bruto) > 1024:
        return "", 204
    try:
        d = json.loads(bruto)
    except ValueError:
        abort(400)
    if not isinstance(d, dict):
        abort(400)
    rota = d.get("rota")
    if not isinstance(rota, str) or rota not in current_app.view_functions or rota == "static" or len(rota) > 60:
        abort(400)
    n = rum.registrar(rota, d.get("m"), d.get("d"), d.get("c") or "")
    db.session.commit()
    return ("", 204 if n else 400)
