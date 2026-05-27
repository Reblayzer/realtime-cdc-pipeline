# FastAPI backend for the storefront + admin dashboard.
#
# Slim image — psycopg[binary] ships its own libpq, clickhouse-driver is
# pure Python, so no apt deps needed.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# uvicorn in production-ish mode: one worker, no reload, structured logs.
# For a real deployment you'd put gunicorn in front and run >1 worker.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/app/log_config.json"]
