"""Auxiliares de resposta HTTP compartilhados pelos blueprints."""
from flask import make_response, render_template, request


def pedido_de_fragmento() -> bool:
    """O navegador (busca ao vivo, app.js) pede só a região de resultados com `X-Fragmento: 1`."""
    return request.headers.get("X-Fragmento") == "1"


def pagina_ou_fragmento(pagina: str, parcial: str, **ctx):
    """Página completa para navegação normal; só o miolo da lista quando é a busca ao vivo (menos bytes e menos HTML renderizado).
    Sem JavaScript o formulário continua funcionando: ele envia o GET comum e recebe a página inteira."""
    resp = make_response(render_template(parcial if pedido_de_fragmento() else pagina, **ctx))
    resp.vary.add("X-Fragmento")  # a mesma URL tem duas respostas: um cache compartilhado não pode misturá-las
    return resp
