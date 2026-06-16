# Dockerfile
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .
COPY config.json .

# Создаем том для хранения данных
VOLUME ["/app/data"]

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV CONFIG_FILE=/app/data/config.json

# Запускаем бота
CMD ["python", "bot.py"]
