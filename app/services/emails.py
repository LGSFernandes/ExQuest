"""Envio de e-mail por SMTP com timeout (substitui o Flask-Mail, que não tem timeout). O envio real roda na fila (services/jobs.py)."""
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

from app.extensions import outbox


class ErroEnvio(Exception):
    pass


def enviar_agora(destino: str, assunto: str, corpo: str) -> None:
    cfg = current_app.config
    if cfg.get("TESTING") or cfg.get("MAIL_SUPPRESS_SEND"):
        outbox.append({"to": destino, "subject": assunto, "body": corpo})
        return
    if not cfg["MAIL_SERVER"]:
        raise ErroEnvio("SMTP não configurado")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, cfg["MAIL_DEFAULT_SENDER"], destino
    msg.set_content(corpo)
    ctx = ssl.create_default_context()
    t = cfg["SMTP_TIMEOUT"]
    try:
        if cfg["MAIL_USE_SSL"]:
            srv = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=t, context=ctx)
        else:
            srv = smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=t)
        with srv:
            if cfg["MAIL_USE_TLS"] and not cfg["MAIL_USE_SSL"]:
                srv.starttls(context=ctx)
            if cfg["MAIL_USERNAME"]:
                srv.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            srv.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        raise ErroEnvio(type(e).__name__) from e
