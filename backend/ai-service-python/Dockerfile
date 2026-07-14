FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

# NOTE on cache persistence in production: Fly.io machine-local disk survives
# restarts/crashes of the same machine but NOT a redeploy. For persistence
# across redeploys, attach a Fly Volume and point TRANSLATION_DB_PATH at it, e.g.:
#   fly volumes create translate_data --size 1
#   # in fly.toml: [[mounts]] source="translate_data" destination="/data"
#   fly secrets set TRANSLATION_DB_PATH=/data/translations.db
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
