# --- Сборка зависимостей ---
FROM python:3.12-slim as builder

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.txt

# --- Финальный образ ---
FROM python:3.12-slim

WORKDIR /usr/src/app

COPY --from=builder /usr/src/app/wheels /wheels
COPY . .

RUN pip install --no-cache /wheels/*

# Копируем ключи, если они есть
COPY keys /app/keys

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]