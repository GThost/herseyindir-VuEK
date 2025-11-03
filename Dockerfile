# Dockerfile
FROM python:3.11-slim

# FFmpeg lazım (mp3 ve video merge için)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -U pip && pip install -r requirements.txt

COPY . .

# Railway genelde PORT verir ama 8080 güvenli
ENV PORT=8080
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
