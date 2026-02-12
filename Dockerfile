FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всех файлов приложения
COPY . .

# Создание директории для базы данных
RUN mkdir -p /app/data

# Открытие порта
EXPOSE 5000

# Переменные окружения
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

# Запуск приложения
CMD ["python", "app.py"]
