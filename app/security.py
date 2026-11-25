"""Utilitários de segurança: validação de entrada, senhas, redirecionamento seguro e decoradores.

Princípio: não "limpar" texto na entrada para tentar impedir XSS/SQLi. Consultas usam parâmetros (ORM) e a saída é
sempre escapada pelo Jinja; filtros por padrão suspeito só rejeitam texto legítimo (ex.: `;` e `--` em matemática)."""
import re
import secrets
import unicodedata
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, request
from flask_login import current_user

_USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")
_RESERVADOS = {"admin", "administrador", "root", "suporte", "exquest", "sistema", "moderador", "api", "static",
               "login", "logout", "registro", "premium", "loja", "perfil", "ranking", "ajuda"}
_SENHAS_COMUNS = {"12345678", "123456789", "1234567890", "password", "senha123", "qwertyuiop", "11111111", "abc12345",
                  "password1", "iloveyou", "12341234", "00000000", "senha1234", "exquest123", "mudar123"}
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")  # controle + bidi override


def limpar_texto(texto: str | None, max_len: int = 2000, multilinha: bool = False) -> str:
    """Normaliza (NFC), remove caracteres de controle/bidi e espaços nas pontas, limita o tamanho. Não altera HTML."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFC", str(texto))
    t = _CTRL_RE.sub("", t.replace("\r\n", "\n").replace("\r", "\n") if multilinha else t.replace("\n", " "))
    return t.strip()[:max_len]


def validar_username(username: str) -> tuple[bool, str]:
    u = (username or "").strip().lower()
    if not _USERNAME_RE.match(u):
        return False, "Use de 3 a 30 caracteres: letras minúsculas, números, ponto e sublinhado."
    if u in _RESERVADOS:
        return False, "Este nome de usuário é reservado."
    return True, ""


def validar_senha(senha: str, *, email: str = "", username: str = "") -> tuple[bool, str]:
    if len(senha or "") < 8:
        return False, "A senha precisa ter pelo menos 8 caracteres."
    if len(senha) > 128:
        return False, "A senha pode ter no máximo 128 caracteres."
    baixa = senha.lower()
    if baixa in _SENHAS_COMUNS or len(set(baixa)) < 4:
        return False, "Essa senha é muito comum. Escolha uma menos previsível."
    for ref in (email.split("@")[0] if email else "", username):
        if ref and len(ref) >= 4 and baixa == ref.lower():
            return False, "A senha não pode ser igual ao seu e-mail ou usuário."
    return True, ""


def url_interna_segura(destino: str | None, padrao: str = "/") -> str:
    """Aceita só caminhos do próprio site (evita open redirect via ?next=)."""
    if not destino:
        return padrao
    base = urlparse(request.host_url)
    alvo = urlparse(urljoin(request.host_url, destino))
    # navegadores tratam "\\" como "/": "/\\evil.com" viraria "//evil.com"
    if "\\" in destino or alvo.scheme not in ("http", "https") or alvo.netloc != base.netloc \
            or not destino.startswith("/") or destino.startswith("//"):
        return padrao
    if alvo.path.startswith("//") or "\\" in alvo.path:  # a normalização de "/.//x" gera "//x" (protocolo relativo)
        return padrao
    return alvo.path + (f"?{alvo.query}" if alvo.query else "")


def ip_usuario() -> str:
    """IP do cliente. `remote_addr` já reflete o proxy confiável (ProxyFix, TRUSTED_PROXIES); nunca ler X-Forwarded-For direto."""
    return request.remote_addr or "desconhecido"


def gerar_tag_unica(existe) -> str:
    """4 caracteres aleatórios sem ambiguidade (sem 0/O/1/I). `existe(tag)` consulta o banco."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(50):
        tag = "".join(secrets.choice(alfabeto) for _ in range(4))
        if not existe(tag):
            return tag
    return "".join(secrets.choice(alfabeto) for _ in range(6))


def admin_required(f):
    @wraps(f)
    def deco(*a, **kw):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*a, **kw)
    return deco
