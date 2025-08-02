FROM python:3.10-slim

# ffmpeg kurulumu
RUN apt update && apt install -y ffmpeg

# çalışma klasörü
WORKDIR /app

# dosyaları kopyala
COPY . /app

# bağımlılıkları yükle
RUN pip install -r requirements.txt

# uygulamayı başlat
CMD ["python", "app.py"]
