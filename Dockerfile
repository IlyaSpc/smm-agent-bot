FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скачиваем шрифт DejaVuSans.ttf из актуального релиза
RUN apt-get update && apt-get install -y wget && \
    wget -O DejaVuSans.ttf https://github.com/dejavu-fonts/dejavu-fonts/raw/ttf-2.37/ttf/DejaVuSans.ttf && \
    apt-get remove -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY bot.py .

CMD ["python", "bot.py"]