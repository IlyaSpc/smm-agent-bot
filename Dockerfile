FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем wget и unzip, скачиваем шрифт, извлекаем и чистим
RUN apt-get update && apt-get install -y wget unzip && \
    wget -O dejavu-fonts.zip https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip && \
    unzip dejavu-fonts.zip -d dejavu-fonts && \
    mv dejavu-fonts/dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf . && \
    rm -rf dejavu-fonts dejavu-fonts.zip && \
    apt-get remove -y wget unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY bot.py .

CMD ["python", "bot.py"]