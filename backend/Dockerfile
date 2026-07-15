FROM python:3.12-slim

# postgresql-client is only used by app.backup against a Postgres deployment
# (the SQLite path uses the sqlite3 online backup API and needs none of this).
# Debian ships client 15, so compose pins postgres:15 to match: pg_dump refuses
# a server newer than itself, and PGDG's client-16 will not resolve against
# this base image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ukr \
        tesseract-ocr-eng \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Alembic scripts: the app lifespan (and the bot) run migrations on startup.
COPY alembic.ini .
COPY alembic ./alembic

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
