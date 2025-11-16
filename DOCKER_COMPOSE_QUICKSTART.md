# ArtStore Docker Compose - Быстрый старт

Краткая инструкция для мгновенного запуска системы ArtStore.

## Структура файлов

```
├── docker-compose.infrastructure.yml  # База: PostgreSQL, Redis, MinIO, PgAdmin
├── docker-compose.backend.yml         # Backend: Admin, Storage, Ingester, Query
├── docker-compose.dev.yml             # Dev override: hot-reload, debug ports
├── docker-compose.full.yml            # All-in-one: infrastructure + backend + monitoring
├── docker-compose.monitoring.yml      # Monitoring: Prometheus, Grafana
└── DOCKER_COMPOSE_GUIDE.md            # Полная документация
```

## 1️⃣ Самый быстрый старт (Production-like)

```bash
# Копируем environment
cp .env.example .env

# ⚠️ ОБЯЗАТЕЛЬНО измените пароли в .env для production!

# Запуск полного стека
docker-compose -f docker-compose.full.yml up -d

# Проверка статуса
docker-compose -f docker-compose.full.yml ps

# Логи
docker-compose -f docker-compose.full.yml logs -f
```

**Access URLs**:
- Admin API: http://localhost:8000
- Storage Element: http://localhost:8010
- Ingester API: http://localhost:8020
- Query API: http://localhost:8030
- Grafana: http://localhost:3000 (admin / admin123)

## 2️⃣ Development с hot-reload

```bash
# Копируем environment
cp .env.example .env

# Запуск dev стека (text logging, hot-reload, debug ports)
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               up --build

# Изменения в коде применяются автоматически!
```

**Debug ports** (для PyCharm/VS Code):
- Admin Module: 5678
- Storage Element 01: 5679
- Ingester Module: 5681
- Query Module: 5682

## 3️⃣ Модульный запуск (Production)

```bash
# 1. Infrastructure
docker-compose -f docker-compose.infrastructure.yml up -d

# 2. Backend
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               up -d

# 3. Monitoring (опционально)
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.monitoring.yml \
               up -d
```

## 4️⃣ Полезные команды

```bash
# Остановка всех сервисов
docker-compose -f docker-compose.full.yml down

# Удаление всех данных (volumes)
docker-compose -f docker-compose.full.yml down -v

# Логи конкретного модуля
docker-compose -f docker-compose.full.yml logs -f admin-module

# Перезапуск модуля
docker-compose -f docker-compose.full.yml restart admin-module

# Пересборка после изменений
docker-compose -f docker-compose.full.yml up --build -d

# Bash внутри контейнера
docker exec -it artstore_admin_module bash

# PostgreSQL access
docker exec -it artstore_postgres psql -U artstore -d artstore_admin
```

## 5️⃣ Первое использование API

```bash
# Получение JWT токена (initial admin service account создается автоматически)
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "auto-generated-uuid",
    "client_secret": "from-env-INITIAL_CLIENT_SECRET"
  }'

# Response: {"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 1800}
```

## 6️⃣ Production Security Checklist

Перед production деплоем в `.env`:

- [ ] `ENVIRONMENT=production`
- [ ] `DB_PASSWORD` - strong random (32+ chars)
- [ ] `REDIS_PASSWORD` - strong random (32+ chars)
- [ ] `MINIO_ROOT_PASSWORD` - strong random (32+ chars)
- [ ] `INITIAL_CLIENT_SECRET` - strong random (32+ chars)
- [ ] `CORS_ALLOW_ORIGINS` - explicit domains (НЕ wildcard!)
- [ ] `LOG_FORMAT=json`
- [ ] `GF_SECURITY_ADMIN_PASSWORD` - strong password

## 7️⃣ Troubleshooting

```bash
# Проверка health checks
docker-compose -f docker-compose.full.yml ps

# Логи всех сервисов
docker-compose -f docker-compose.full.yml logs --tail=100

# Очистка и перезапуск
docker-compose -f docker-compose.full.yml down -v
docker-compose -f docker-compose.full.yml up -d
```

## 📚 Дополнительно

Полная документация: **DOCKER_COMPOSE_GUIDE.md**

- Детальные сценарии использования
- Development workflow
- Production deployment
- Monitoring setup
- Advanced troubleshooting
