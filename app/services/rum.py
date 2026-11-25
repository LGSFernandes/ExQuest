"""Monitoramento de velocidade com usuários reais (RUM): grava Core Web Vitals e resume por rota (p75, o percentil usado pelo Google)."""
from datetime import timedelta

from sqlalchemy import delete, select

from app import clock
from app.extensions import db
from app.models import MetricaRum

# nome: (limite "bom", limite "ruim") segundo web.dev; unidade ms, exceto CLS
LIMITES = {"LCP": (2500, 4000), "INP": (200, 500), "CLS": (0.1, 0.25), "FCP": (1800, 3000), "TTFB": (800, 1800)}
MAXIMO = {"LCP": 60000, "INP": 60000, "CLS": 10, "FCP": 60000, "TTFB": 60000}
DISPOSITIVOS = ("movel", "desktop")
CONEXOES = ("", "4g", "3g", "2g", "slow-2g")


def registrar(rota: str, metricas: dict, dispositivo: str, conexao: str) -> int:
    """Valida tudo (o corpo vem do navegador do usuário) e grava. Devolve quantas métricas foram aceitas."""
    if dispositivo not in DISPOSITIVOS or conexao not in CONEXOES or not isinstance(metricas, dict):
        return 0
    n = 0
    for nome, v in metricas.items():
        if nome not in LIMITES or isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 <= v <= MAXIMO[nome]) or v != v:
            continue
        db.session.add(MetricaRum(rota=rota, nome=nome, valor=float(v), dispositivo=dispositivo, conexao=conexao))
        n += 1
    return n


def _p75(valores: list[float]) -> float:
    v = sorted(valores)
    return v[min(len(v) - 1, int(0.75 * len(v)))]


def classificar(nome: str, valor: float) -> str:
    bom, ruim = LIMITES[nome]
    return "bom" if valor <= bom else ("ruim" if valor > ruim else "medio")


def resumo(dias: int = 7, dispositivo: str | None = None, limite: int = 50000) -> list[dict]:
    """p75 por (rota, métrica) nos últimos `dias`. Lê no máximo `limite` linhas (as mais recentes)."""
    q = select(MetricaRum.rota, MetricaRum.nome, MetricaRum.valor).where(MetricaRum.criado_em >= clock.agora() - timedelta(days=dias))
    if dispositivo:
        q = q.where(MetricaRum.dispositivo == dispositivo)
    grupos: dict[tuple[str, str], list[float]] = {}
    for rota, nome, valor in db.session.execute(q.order_by(MetricaRum.id.desc()).limit(limite)):
        grupos.setdefault((rota, nome), []).append(valor)
    return sorted(({"rota": r, "nome": n, "amostras": len(v), "p75": (p := _p75(v)), "nivel": classificar(n, p)}
                   for (r, n), v in grupos.items()), key=lambda x: (x["rota"], x["nome"]))


def limpar_antigos(dias: int) -> int:
    r = db.session.execute(delete(MetricaRum).where(MetricaRum.criado_em < clock.agora() - timedelta(days=dias)))
    db.session.commit()
    return r.rowcount or 0
