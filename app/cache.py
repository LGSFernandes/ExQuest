"""Cache de dados muito consultados. Redis quando REDIS_URL existe; senão memória do processo (válida para 1 instância).

Regras:
    - só guarda dados JSON simples (listas/dicionários/números/texto), nunca objetos ORM nem dados pessoais sensíveis;
    - falha do Redis nunca derruba a requisição: o valor é recalculado (e um aviso é registrado, no máximo 1x por minuto);
    - invalidação por prefixo usa um contador de "geração" (bump), sem varrer chaves.
"""
import json
import logging
import threading
import time
from collections import OrderedDict

from flask import current_app

log = logging.getLogger(__name__)
_MAX_MEM = 2000


class _Memoria:
    def __init__(self):
        self._d: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, k):
        with self._lock:
            v = self._d.get(k)
            if not v:
                return None
            if v[0] < time.monotonic():
                self._d.pop(k, None)
                return None
            self._d.move_to_end(k)
            return v[1]

    def set(self, k, valor, ttl):
        with self._lock:
            self._d[k] = (time.monotonic() + ttl, valor)
            self._d.move_to_end(k)
            while len(self._d) > _MAX_MEM:
                self._d.popitem(last=False)

    def delete(self, k):
        with self._lock:
            self._d.pop(k, None)

    def incr(self, k):
        with self._lock:
            v = self._d.get(k)
            n = int(v[1]) + 1 if v else 1
            self._d[k] = (time.monotonic() + 86400 * 30, str(n))
            return n

    def limpar(self):
        with self._lock:
            self._d.clear()


_mem = _Memoria()
_redis = {"url": None, "cli": None}
_aviso = [0.0]


def _cliente():
    url = current_app.config.get("REDIS_URL") or ""
    if not url:
        return None
    if _redis["url"] != url:
        import redis
        _redis["cli"] = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True,
                                             health_check_interval=30)
        _redis["url"] = url
    return _redis["cli"]


def _falha(e):
    if time.monotonic() - _aviso[0] > 60:
        _aviso[0] = time.monotonic()
        log.warning("cache Redis indisponível (%s); usando o banco direto", type(e).__name__)


def _chave(k: str) -> str:
    return f"{current_app.config.get('CACHE_PREFIXO', 'exq')}:{k}"


def _ler(k):
    c = _cliente()
    if c is None:
        return _mem.get(k)
    try:
        return c.get(k)
    except Exception as e:  # noqa: BLE001 - qualquer falha de rede vira "sem cache"
        _falha(e)
        return None


def _gravar(k, v, ttl):
    c = _cliente()
    if c is None:
        return _mem.set(k, v, ttl)
    try:
        c.set(k, v, ex=ttl)
    except Exception as e:  # noqa: BLE001
        _falha(e)


def geracao(ns: str) -> int:
    """Número atual da 'geração' do namespace; mudar a geração invalida todas as chaves daquele namespace."""
    k = _chave(f"g:{ns}")
    v = _ler(k)
    try:
        return int(v) if v is not None else 0
    except ValueError:
        return 0


def invalidar(ns: str) -> None:
    k = _chave(f"g:{ns}")
    c = _cliente()
    if c is None:
        _mem.incr(k)
        return
    try:
        c.incr(k)
    except Exception as e:  # noqa: BLE001
        _falha(e)


def remover(k: str) -> None:
    k = _chave(k)
    c = _cliente()
    if c is None:
        return _mem.delete(k)
    try:
        c.delete(k)
    except Exception as e:  # noqa: BLE001
        _falha(e)


def obter(ns: str, sub: str, ttl: int, calcular):
    """Devolve o valor em cache de (ns, sub) ou chama `calcular()` e guarda. O resultado precisa ser serializável em JSON."""
    if current_app.config.get("CACHE_DESLIGADO"):
        return calcular()
    k = _chave(f"{ns}:{geracao(ns)}:{sub}")
    bruto = _ler(k)
    if bruto is not None:
        try:
            return json.loads(bruto)
        except ValueError:
            pass
    valor = calcular()
    _gravar(k, json.dumps(valor, separators=(",", ":"), default=str), ttl)
    return valor


def limpar_tudo_memoria() -> None:  # testes
    _mem.limpar()
