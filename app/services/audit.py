from app.extensions import db
from app.models import LogAuditoria
from app.security import ip_usuario


def registrar(acao: str, usuario_id=None, detalhe: str = "", resultado: str = "ok", *, request=None) -> None:
    """Adiciona ao log de auditoria (o chamador faz o commit). Nunca grave segredos em `detalhe`."""
    ip = ua = ""
    if request is not None:
        ip, ua = ip_usuario(), request.headers.get("User-Agent", "")
    db.session.add(LogAuditoria(usuario_id=usuario_id, acao=acao[:100], detalhe=(detalhe or "")[:500],
                                ip=ip[:50], user_agent=ua[:300], resultado=resultado))
