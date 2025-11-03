FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -U pip && pip install -r requirements.txt
COPY . .

ENV PORT=8080
# Healthcheck (opsiyonel ama iyi)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8080/ping || exit 1

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
