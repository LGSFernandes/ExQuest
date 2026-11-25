"""Níveis e XP (funções puras). Os 10 primeiros limiares são os originais do ExQuest;
acima do nível 10 cada nível custa +4000 XP, para que as recompensas dos níveis 20..100 sejam alcançáveis."""

_BASE = [0, 100, 300, 600, 1000, 1500, 2500, 4000, 6000, 9000]  # início dos níveis 1..10
PASSO_ALEM_10 = 4000
NIVEL_MAX = 100


def xp_inicio_do_nivel(nivel: int) -> int:
    nivel = max(1, min(nivel, NIVEL_MAX))
    return _BASE[nivel - 1] if nivel <= 10 else _BASE[-1] + (nivel - 10) * PASSO_ALEM_10


def nivel_por_xp(xp: int) -> int:
    xp = max(0, xp or 0)
    if xp >= _BASE[-1]:
        return min(NIVEL_MAX, 10 + (xp - _BASE[-1]) // PASSO_ALEM_10)
    return max(i + 1 for i, v in enumerate(_BASE) if xp >= v)


def xp_proximo_nivel(nivel: int) -> int:
    return xp_inicio_do_nivel(min(nivel + 1, NIVEL_MAX))


def progresso(xp: int) -> int:
    n = nivel_por_xp(xp)
    if n >= NIVEL_MAX:
        return 100
    a, b = xp_inicio_do_nivel(n), xp_inicio_do_nivel(n + 1)
    return int((xp - a) * 100 / (b - a))


def recompensa_nivel_catalogo() -> dict[int, dict]:
    """Recompensas por nível alcançado (moedas + cosmético opcional por slug do catálogo)."""
    return {
        5:   {"moedas": 30,   "item": None},
        10:  {"moedas": 80,   "item": None},
        20:  {"moedas": 150,  "item": "badge-veterano"},
        30:  {"moedas": 200,  "item": None},
        50:  {"moedas": 400,  "item": "badge-mestre"},
        75:  {"moedas": 600,  "item": "border-galaxia"},
        100: {"moedas": 1000, "item": "badge-lenda"},
    }
