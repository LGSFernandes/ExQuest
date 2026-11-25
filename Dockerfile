FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production \
    WEB_WORKERS=2 WEB_THREADS=4
RUN useradd -m -u 1000 app
WORKDIR /srv
COPY requirements.txt requirements-postgres.txt ./
# psycopg só é necessário com PostgreSQL; ele entra sempre para a mesma imagem servir os dois bancos
RUN pip install --no-cache-dir -r requirements-postgres.txt
COPY --chown=app:app . .
RUN mkdir -p instance app/static/data && chown -R app:app instance app/static/data
USER app
EXPOSE 8000
# Migrações NÃO rodam aqui: com várias réplicas elas disputariam o banco. O serviço `migrar` do compose roda uma vez.
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:8000 -w ${WEB_WORKERS} --threads ${WEB_THREADS} --worker-class gthread --max-requests 2000 --max-requests-jitter 200 --graceful-timeout 20 --timeout 60 main:app"]
