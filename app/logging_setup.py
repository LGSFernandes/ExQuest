import json
import logging
import sys
from datetime import datetime, timezone

from flask import g, has_request_context, request


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if has_request_context():
            data["request_id"] = getattr(g, "request_id", None)
            data["path"] = request.path
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def configure_logging(app) -> None:
    handler = logging.StreamHandler(sys.stderr)
    if app.config["LOG_JSON"] or app.config["IS_PRODUCTION"]:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(app.config["LOG_LEVEL"])
    # nunca registrar corpo de requisições (podem conter senhas/tokens)
    logging.getLogger("werkzeug").setLevel(logging.WARNING if app.config["IS_PRODUCTION"] else logging.INFO)
