FROM python:3.11-slim

# Устанавливаем ffmpeg для голоса
RUN apt-get update && apt-get install -y ffmpeg

# Рабочая директория
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]