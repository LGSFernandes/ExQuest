"""Itens de navegação. Só aparecem os que têm rota registrada (blueprints entram aos poucos)."""
from flask import current_app

# (endpoint, rótulo, ícone, grupo, aparece na barra inferior do celular)
ITENS = [
    ("main.inicio", "Início", "house", "Estudo", True),
    ("questoes.index", "Questões", "book-open", "Estudo", True),
    ("missoes.index", "Missões", "target", "Estudo", False),
    ("simulados.escolher", "Simulados", "list-checks", "Estudo", False),
    ("revisao.index", "Revisão", "repeat", "Estudo", False),
    ("colecoes.index", "Coleções", "bookmark", "Estudo", False),
    ("ranking.index", "Ranking", "trophy", "Competir", True),
    ("competicoes.index", "Competições", "swords", "Competir", False),
    ("social.amigos", "Amigos", "users", "Social", False),
    ("social.chat", "Mensagens", "message-circle", "Social", False),
    ("loja.index", "Loja", "store", "Loja", True),
    ("loja.inventario", "Inventário", "backpack", "Loja", False),
    ("pagamentos.moedas", "Moedas", "coins", "Loja", False),
    ("pagamentos.premium_pagina", "Premium", "crown", "Loja", False),
    ("perfil.meu", "Perfil", "user", "Conta", True),
    ("perfil.configuracoes", "Configurações", "settings", "Conta", False),
]


def itens_visiveis():
    vf = current_app.view_functions
    return [i for i in ITENS if i[0] in vf]
