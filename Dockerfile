FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Geen media/ of .env — media staat in R2, secrets via Fly.io
COPY app.py db.py config.py users_db.py mailer.py ./
COPY templates/ templates/
COPY static/ static/

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --timeout 120 app:app"]
