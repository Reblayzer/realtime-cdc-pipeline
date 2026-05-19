# Minimal Python image for the workload simulator.
# Kept slim — no system deps needed because psycopg[binary] ships its own libpq.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generate.py .

# Unbuffered stdout so docker compose logs sees output in real time.
ENV PYTHONUNBUFFERED=1

CMD ["python", "generate.py"]
