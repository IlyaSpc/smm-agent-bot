# Базовый образ с Python 3.11
FROM python:3.11-slim

# Устанавливаем Java
RUN apt-get update && apt-get install -y openjdk-17-jre && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY bot.py .

# Запускаем бота
CMD ["python", "bot.py"]