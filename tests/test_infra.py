"""Infra: .env.example cobre toda variável lida pela configuração; compose/nginx coerentes com o app."""
import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
INTERNAS = {"APP_ENV", "FLASK_ENV", "PYTEST_CURRENT_TEST"}  # lidas, mas não são configuração do operador


def test_env_example_documenta_toda_variavel_da_config():
    codigo = (RAIZ / "app" / "config.py").read_text()
    usadas = set(re.findall(r'(?:getenv|_int|_bool|environ\.get)\(\s*"([A-Z][A-Z0-9_]+)"', codigo)) - INTERNAS
    exemplo = (RAIZ / ".env.example").read_text()
    faltando = sorted(v for v in usadas if not re.search(rf"^#?\s*{v}=", exemplo, re.M))
    assert not faltando, f"variáveis sem entrada em .env.example: {faltando}"


def test_compose_separa_migracao_worker_e_web_escalavel():
    c = yaml.safe_load((RAIZ / "docker-compose.yml").read_text())["services"]
    assert {"migrar", "web", "proxy", "worker", "tarefas"} <= set(c)
    assert "ports" not in c["web"]  # escalável: sem porta fixa no host, o proxy distribui
    assert "jobs-worker" in " ".join(c["worker"]["command"])
    for nome in ("web", "worker", "tarefas"):
        assert c[nome]["environment"]["APP_ENV"] == "production"
        assert c[nome]["depends_on"]["migrar"]["condition"] == "service_completed_successfully"
    assert c["web"]["environment"]["JOBS_MODE"] == "queue" and "healthcheck" in c["web"]
    assert "--scale" not in (RAIZ / "Dockerfile").read_text() and "migrar" not in (RAIZ / "Dockerfile").read_text().split("CMD")[1]


def test_nginx_balanceia_e_usa_cache_imutavel():
    for arq in ("nginx.conf", "nginx.compose.conf"):
        t = (RAIZ / "deploy" / arq).read_text()
        assert "least_conn" in t and "proxy_next_upstream" in t, arq
    assert "immutable" in (RAIZ / "deploy" / "nginx.conf").read_text()
