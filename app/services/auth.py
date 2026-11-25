"""Regras de autenticação: tokens de recuperação em hash, bloqueio por tentativas, criação de conta."""
import hashlib
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import func, select

from app import clock
from app.extensions import bcrypt, db
from app.models import LogAuditoria, TokenRecuperacao, Usuario
from app.security import gerar_tag_unica

MAX_FALHAS = 8
JANELA_FALHAS = timedelta(minutes=15)
VALIDADE_TOKEN = timedelta(hours=1)
# hash usado quando o e-mail não existe: gasta o mesmo tempo do bcrypt e evita enumerar contas pelo tempo de resposta
_HASH_FALSO = None


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _chave_falha(email: str) -> str:
    return "e:" + hashlib.sha256(email.lower().encode()).hexdigest()[:16]


def falhas_recentes(email: str) -> int:
    desde = clock.agora() - JANELA_FALHAS
    return db.session.scalar(select(func.count(LogAuditoria.id)).where(
        LogAuditoria.acao == "login_falha", LogAuditoria.detalhe == _chave_falha(email), LogAuditoria.criado_em >= desde)) or 0


def bloqueado(email: str) -> bool:
    return falhas_recentes(email) >= MAX_FALHAS


def registrar_falha(email: str, ip: str) -> None:
    db.session.add(LogAuditoria(acao="login_falha", detalhe=_chave_falha(email), ip=ip[:50], resultado="falha"))


def verificar_credenciais(email: str, senha: str) -> Usuario | None:
    u = Usuario.query.filter_by(email=(email or "").strip().lower()).first()
    global _HASH_FALSO
    if _HASH_FALSO is None:
        _HASH_FALSO = bcrypt.generate_password_hash("senha-inexistente").decode()
    hash_ = u.senha_hash if (u and u.senha_hash) else _HASH_FALSO
    ok = bcrypt.check_password_hash(hash_, senha or "")
    return u if (ok and u and u.senha_hash) else None


def criar_conta(*, nome, sobrenome, username, email, senha=None, google_id=None) -> Usuario:
    u = Usuario(nome=nome, sobrenome=sobrenome, username=username.lower(), email=email.lower(), google_id=google_id,
                senha_hash=bcrypt.generate_password_hash(senha).decode() if senha else None,
                tag=gerar_tag_unica(lambda t: Usuario.query.filter_by(tag=t).first() is not None))
    db.session.add(u)
    db.session.flush()
    return u


def username_livre(base: str) -> str:
    import re
    b = re.sub(r"[^a-z0-9_.]", "", base.lower())[:24] or "aluno"
    if len(b) < 3:
        b += "000"[: 3 - len(b)]
    cand, i = b, 0
    while Usuario.query.filter_by(username=cand).first():
        i += 1
        cand = f"{b}{secrets.randbelow(9000) + 1000}" if i > 3 else f"{b}{i}"
    return cand


def criar_token_recuperacao(u: Usuario) -> str:
    """Devolve o token em claro (vai só por e-mail); no banco fica apenas o SHA-256."""
    TokenRecuperacao.query.filter_by(usuario_id=u.id, usado=False).update({"usado": True})
    token = secrets.token_urlsafe(32)
    db.session.add(TokenRecuperacao(usuario_id=u.id, token=_sha(token), expira=clock.agora() + VALIDADE_TOKEN))
    return token


def token_valido(token: str) -> TokenRecuperacao | None:
    t = TokenRecuperacao.query.filter_by(token=_sha(token)).first()
    return t if t and t.valido else None


def redefinir_senha(t: TokenRecuperacao, nova: str) -> bool:
    """Consome o token com UPDATE condicional: de dois envios simultâneos só um vence. False = já usado/expirado."""
    gasto = TokenRecuperacao.query.filter(TokenRecuperacao.id == t.id, TokenRecuperacao.usado.is_(False),
                                          TokenRecuperacao.expira > clock.agora()).update({"usado": True}, synchronize_session=False)
    if gasto != 1:
        return False
    u = t.usuario
    u.senha_hash = bcrypt.generate_password_hash(nova).decode()
    u.session_version = (u.session_version or 0) + 1  # derruba as sessões abertas
    TokenRecuperacao.query.filter_by(usuario_id=u.id, usado=False).update({"usado": True})
    return True


def enviar_email_recuperacao(u: Usuario, link: str) -> bool:
    cfg = current_app.config
    if not cfg["MAIL_SERVER"]:
        if not cfg["IS_PRODUCTION"]:
            current_app.logger.warning("SMTP não configurado; link de recuperação (apenas desenvolvimento): %s", link)
        return False
    from app.services import jobs
    corpo = (f"Olá, {u.nome}.\n\nRecebemos um pedido para redefinir sua senha. O link abaixo vale por 1 hora:\n{link}\n\n"
             "Se não foi você, ignore este e-mail: sua senha continua a mesma.")
    jobs.enfileirar("email", {"to": u.email, "subject": "Redefinição de senha — ExQuest", "body": corpo})
    return True
