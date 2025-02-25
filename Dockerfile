FROM python:3.11-slim

RUN apt-get update && apt-get install -y openjdk-17-jre && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скачиваем шрифт DejaVuSans.ttf
RUN apt-get update && apt-get install -y wget && \
    wget -O DejaVuSans.ttf https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf && \
    apt-get remove -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY bot.py .

CMD ["python", "bot.py"]