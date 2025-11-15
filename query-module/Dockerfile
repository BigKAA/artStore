# Multi-stage Dockerfile для Query Module
# Stage 1: Builder - установка зависимостей
# Stage 2: Runtime - минимальный production образ

FROM python:3.11-slim AS builder

WORKDIR /build

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .

# Создание venv и установка зависимостей
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ========================================
# Stage 2: Runtime - production образ
# ========================================
FROM python:3.11-slim

WORKDIR /app

# Установка runtime зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование venv из builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Создание non-root пользователя
RUN useradd -m -u 1000 queryuser && \
    chown -R queryuser:queryuser /app

# Копирование application code
COPY --chown=queryuser:queryuser . .

# Переключение на non-root user
USER queryuser

# Environment variables (будут переопределены в docker-compose.yml)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8030/health/live || exit 1

# Expose port
EXPOSE 8030

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8030"]
