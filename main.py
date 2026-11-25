"""Ponto de entrada para desenvolvimento local: `python main.py`.
Em produção use um servidor WSGI (veja docs/GUIA_DE_INSTALACAO_E_DESENVOLVIMENTO.md): `gunicorn "main:app"`."""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # O depurador do Werkzeug executa código arbitrário: só liga se FLASK_DEBUG=1 for escolhido de propósito.
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
