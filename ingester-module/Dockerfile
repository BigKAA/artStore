# Multi-stage Dockerfile для Ingester Module
# Stage 1: Builder - установка зависимостей
# Stage 2: Runtime - минимальный production образ

# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.12-slim as builder

# Метаданные
LABEL maintainer="artstore-team"
LABEL description="ArtStore Ingester Module - Builder Stage"

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Создание виртуального окружения
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копирование requirements.txt
COPY requirements.txt /tmp/requirements.txt

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# ============================================
# Stage 2: Test - для запуска тестов
# ============================================
FROM python:3.12-slim as test

# Метаданные
LABEL maintainer="artstore-team"
LABEL description="ArtStore Ingester Module - Test Stage"

# Установка системных зависимостей для тестирования
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование виртуального окружения из builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Установка тестовых зависимостей
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    pytest-mock \
    httpx \
    cryptography

# Установка рабочей директории
WORKDIR /app

# Копирование приложения и тестов
COPY ./app /app/app
COPY ./tests /app/tests
COPY ./pytest.ini /app/pytest.ini

# Environment variables для тестирования
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TESTING=true \
    LOG_FORMAT=text

# Команда по умолчанию - запуск тестов
CMD ["pytest", "tests/", "-v", "--cov=app", "--cov-report=term"]

# ============================================
# Stage 3: Runtime
# ============================================
FROM python:3.12-slim

# Метаданные
LABEL maintainer="artstore-team"
LABEL description="ArtStore Ingester Module - Production Runtime"
LABEL version="0.1.0"

# Создание непривилегированного пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Установка runtime зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование виртуального окружения из builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Установка рабочей директории
WORKDIR /app

# Копирование приложения
COPY ./app /app/app

# Создание директории для ключей и логов
RUN mkdir -p /app/keys /app/logs && \
    chown -R appuser:appuser /app

# Переключение на непривилегированного пользователя
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_FORMAT=json \
    APP_HOST=0.0.0.0 \
    APP_PORT=8020

# Expose port
EXPOSE 8020

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8020/api/v1/health/live || exit 1

# Запуск приложения
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]
