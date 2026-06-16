FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY bot.py .
COPY config.json .

# Создаем папку для данных
RUN mkdir -p /app/data

# Переменные
ENV PYTHONUNBUFFERED=1
ENV CONFIG_FILE=/app/data/config.json

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import sys; sys.exit(0)" || exit 1

# Запуск
CMD ["python", "bot.py"]
