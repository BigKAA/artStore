# Multi-stage Dockerfile for ArtStore Admin Module
# Production-ready image with minimal size

# Stage 1: Builder - установка зависимостей
FROM python:3.12-slim AS builder

# Установка системных зависимостей для компиляции Python пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libldap2-dev \
    libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

# Создание виртуального окружения
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - минимальный production образ
FROM python:3.12-slim

# Метаданные образа
LABEL maintainer="ArtStore Team"
LABEL version="0.1.0"
LABEL description="ArtStore Admin Module - Authentication and Management API"

# Установка runtime зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libldap2 \
    libsasl2-2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создание непривилегированного пользователя
RUN groupadd -r artstore && useradd -r -g artstore artstore

# Копирование виртуального окружения из builder stage
COPY --from=builder /opt/venv /opt/venv

# Установка рабочей директории
WORKDIR /app

# Копирование application code
COPY --chown=artstore:artstore . .

# Переменные окружения
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Health check (с увеличенным start-period для инициализации БД и Redis)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Переключение на непривилегированного пользователя
USER artstore

# Expose порт
EXPOSE 8000

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
