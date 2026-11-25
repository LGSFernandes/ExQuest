"""Catálogo da loja versionado em código. `semear()` é idempotente: cria o que falta e NUNCA altera preço,
nome ou ativação de item que já existe (o banco real tem itens e compras). A identidade é `css_class`
(ou o nome, nos itens sem classe) e o slug é a própria `css_class`."""
import re

from sqlalchemy import select

from app.extensions import db
from app.models import ItemLoja

B, E, F, BD = "borda", "efeito", "fundo", "badge"
ITENS = [
    # bordas do avatar
    (B, "Borda Prata", "Anel prateado suave ao redor do avatar.", "comum", 80, "border-prata"),
    (B, "Borda Ouro", "Anel dourado clássico.", "raro", 200, "border-dourada"),
    (B, "Borda Neon Roxo", "Borda neon roxa com brilho pulsante.", "epico", 500, "border-neon-roxo"),
    (B, "Borda Neon Azul", "Borda neon azul elétrico vibrante.", "epico", 550, "border-neon-azul"),
    (B, "Borda Chamas", "Anel laranja com chamas em movimento.", "epico", 750, "border-chamas"),
    (B, "Borda Gelo", "Cristais de gelo azuis girando devagar.", "epico", 800, "border-gelo"),
    (B, "Borda Galáxia", "Gradiente cônico girando como uma galáxia.", "lendario", 2000, "border-galaxia"),
    (B, "Borda Arco-Íris", "Arco-íris animado girando sem parar.", "lendario", 2500, "border-rainbow"),
    (B, "Borda Plasma", "Plasma bicolor com pulso elétrico.", "lendario", 3000, "border-plasma"),
    (B, "Borda Dourada Rara", "Dupla camada dourada com brilho animado.", "lendario", 3500, "border-gold-rare"),
    # efeitos de fundo do perfil (animados, só CSS, ficam atrás dos cards)
    (E, "Efeito Aurora", "Aurora boreal suave se movendo ao fundo.", "raro", 300, "efeito-aurora"),
    (E, "Efeito Cosmos", "Campo de estrelas cintilantes.", "epico", 600, "efeito-cosmos"),
    (E, "Efeito Matrix", "Colunas de luz verde descendo.", "epico", 800, "efeito-matrix"),
    (E, "Partículas Douradas", "Pontos dourados flutuando devagar.", "lendario", 1800, "efeito-particles-gold"),
    (E, "Partículas Roxas", "Pontos lilás flutuando devagar.", "lendario", 1800, "efeito-particles-purple"),
    (E, "Partículas Azuis", "Pontos azul neon flutuando devagar.", "lendario", 1800, "efeito-particles-blue"),
    (E, "Efeito Fogo", "Brasas subindo pelo fundo do perfil.", "lendario", 2200, "efeito-fogo"),
    (E, "Efeito Trovão", "Clarões azuis cruzando o fundo.", "lendario", 2200, "efeito-trovao"),
    (E, "Efeito Chuva", "Gotas de chuva caindo ao fundo.", "epico", 900, "efeito-chuva"),
    (E, "Efeito Bokeh", "Luzes desfocadas à deriva.", "raro", 400, "efeito-bokeh"),
    # fundos estáticos do perfil
    (F, "Fundo Papel Pautado", "Linhas de caderno sobre papel claro.", "comum", 120, "fundo-pautado"),
    (F, "Fundo Quadriculado", "Folha de caderno quadriculado.", "comum", 120, "fundo-quadriculado"),
    (F, "Fundo Pontilhado", "Grade de pontos de bullet journal.", "comum", 150, "fundo-pontilhado"),
    (F, "Fundo Lousa", "Verde de lousa com giz.", "raro", 300, "fundo-lousa"),
    (F, "Fundo Marca-Texto", "Faixas diagonais de marca-texto.", "raro", 350, "fundo-marca-texto"),
    (F, "Fundo Topográfico", "Curvas de nível de um mapa.", "epico", 700, "fundo-topografico"),
    (F, "Fundo Constelação", "Céu noturno com constelações.", "epico", 900, "fundo-constelacao"),
    (F, "Fundo Crepúsculo", "Degradê de fim de tarde.", "epico", 900, "fundo-crepusculo"),
    # badges
    (BD, "Badge Estudante", "Para quem está começando a jornada.", "comum", 50, "badge-estudante"),
    (BD, "Badge Veterano", "Veterano da plataforma.", "raro", 400, "badge-veterano"),
    (BD, "Badge Mestre", "Mestre, com brilho especial.", "epico", 1200, "badge-mestre"),
    (BD, "Badge Lenda", "Lendária, com partículas.", "lendario", 4000, "badge-lenda"),
]
CONSUMIVEIS = [  # (tipo, nome, descrição, raridade, preço, % ou cargas, horas)
    ("boost_xp", "Boost XP +50% (24h)", "Aumenta o ganho de XP em 50% por 24h.", "comum", 120, 50, 24),
    ("boost_xp", "Boost XP +100% (48h)", "Dobra o ganho de XP por 48h.", "raro", 350, 100, 48),
    ("boost_moeda", "Boost Moedas +50% (24h)", "Aumenta o ganho de moedas em 50% por 24h.", "comum", 100, 50, 24),
    ("boost_moeda", "Boost Moedas +100% (48h)", "Dobra o ganho de moedas por 48h.", "raro", 300, 100, 48),
    ("streak_shield", "Escudo de Streak", "Cobre 1 dia sem estudar.", "raro", 180, 1, 0),
    ("streak_shield", "Escudo Duplo", "Cobre 2 dias sem estudar.", "epico", 400, 2, 0),
]


def _slug(t: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", t.lower().replace("+", "")))[:80].strip("-")


def semear() -> tuple[int, int]:
    """Devolve (criados, ja_existiam). O chamador faz o commit."""
    criados = existentes = 0
    desejados = [dict(tipo=t, nome=n, descricao=d, raridade=r, preco=p, css_class=c, slug=c) for t, n, d, r, p, c in ITENS]
    desejados += [dict(tipo=t, nome=n, descricao=d, raridade=r, preco=p, valor_boost=v, duracao_h=h, slug=_slug(n))
                  for t, n, d, r, p, v, h in CONSUMIVEIS]
    for ordem, d in enumerate(desejados, 1):
        crit = ItemLoja.css_class == d["css_class"] if d.get("css_class") else (ItemLoja.nome == d["nome"])
        item = db.session.scalar(select(ItemLoja).where(crit))
        if item is not None:
            existentes += 1
            if not item.slug and not db.session.scalar(select(ItemLoja.id).where(ItemLoja.slug == d["slug"])):
                item.slug = d["slug"]
            continue
        if db.session.scalar(select(ItemLoja.id).where(ItemLoja.slug == d["slug"])):
            d["slug"] = f"{d['slug']}-novo"
        db.session.add(ItemLoja(ordem=ordem * 10, ativo=True, **d))
        criados += 1
    return criados, existentes
