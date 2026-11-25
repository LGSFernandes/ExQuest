"""Catálogo único de planos e direitos (entitlements). Preços em centavos de BRL.
O servidor decide TODO benefício a partir daqui — nunca o navegador."""

PLANOS = {
    "basic": {"nome": "Básico", "cor": "#8fa3b8", "mensal": 990, "anual": 9490},
    "inter": {"nome": "Intermediário", "cor": "#f2b84b", "mensal": 1990, "anual": 17990},
    "advan": {"nome": "Avançado", "cor": "#c6f135", "mensal": 3990, "anual": 33490},
}
CICLOS = {"mensal": 30, "anual": 365}  # dias de acesso por pagamento
ORDEM = {None: 0, "basic": 1, "inter": 2, "advan": 3}

# None = ilimitado. Chave None = plano gratuito.
LIMITES = {
    "questoes_dia":         {None: 3,  "basic": 15, "inter": 30, "advan": None},
    "simulados_dia":        {None: 1,  "basic": 3,  "inter": 7,  "advan": None},
    "max_questoes_simulado": {None: 5, "basic": 15, "inter": 20, "advan": 50},
    "amigos":               {None: 15, "basic": 50, "inter": 100, "advan": None},
    "grupos":               {None: 5,  "basic": 20, "inter": 40, "advan": None},
    "torneios_mes":         {None: 0,  "basic": 0,  "inter": 3,  "advan": None},
    "colecoes":             {None: 3,  "basic": 10, "inter": 25, "advan": None},
    "boost_pct":            {None: 0,  "basic": 10, "inter": 15, "advan": 30},
}
RECURSOS = {  # booleanos
    "upload_gif":      {None: False, "basic": True, "inter": True, "advan": True},
    "upload_banner":   {None: False, "basic": False, "inter": True, "advan": True},
    "nick_cor":        {None: False, "basic": False, "inter": True, "advan": True},
    "nick_gradiente":  {None: False, "basic": False, "inter": False, "advan": True},
    "nick_fonte":      {None: False, "basic": False, "inter": False, "advan": True},
    "tag_custom":      {None: False, "basic": False, "inter": False, "advan": True},
    "competicoes":     {None: False, "basic": False, "inter": True, "advan": True},
    "relatorio_completo": {None: False, "basic": False, "inter": True, "advan": True},
}


def limite(chave: str, plano: str | None):
    return LIMITES[chave][plano]


def recurso(chave: str, plano: str | None) -> bool:
    return RECURSOS[chave][plano]


def beneficios(plano: str) -> list[str]:
    """Texto dos benefícios, gerado dos mesmos números que o servidor aplica."""
    def n(v, un):
        return "ilimitados" if v is None else f"{v} {un}"
    L = lambda c: LIMITES[c][plano]  # noqa: E731
    R = lambda c: RECURSOS[c][plano]  # noqa: E731
    out = [
        f"Questões: {n(L('questoes_dia'), 'por dia')}",
        f"Simulados: {n(L('simulados_dia'), 'por dia')}, até {L('max_questoes_simulado')} questões",
        f"Boost permanente de {L('boost_pct')}% em XP e moedas",
        f"Amigos: {n(L('amigos'), '')}".strip() + " · Grupos: " + n(L('grupos'), '').strip(),
        f"Coleções de questões: {n(L('colecoes'), '')}".strip(),
    ]
    if R("upload_gif"):
        out.append("GIF animado como foto de perfil")
    if R("upload_banner"):
        out.append("Banner personalizado (inclusive GIF)")
    if R("nick_cor"):
        out.append("Cor personalizada no nome")
    if R("nick_gradiente"):
        out.append("Gradiente e fonte personalizados no nome")
    if R("tag_custom"):
        out.append("Tag personalizada")
    if R("competicoes"):
        t = L("torneios_mes")
        out.append("Competições " + ("ilimitadas" if t is None else f"({t} por mês)"))
    if R("relatorio_completo"):
        out.append("Relatório completo de evolução")
    return out


def preco_centavos(plano: str, ciclo: str) -> int:
    return PLANOS[plano][ciclo]


def formatar_brl(centavos: int) -> str:
    return f"R$ {centavos / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
