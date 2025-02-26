FROM python:3.11-slim

# Устанавливаем ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Устанавливаем зависимости Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]