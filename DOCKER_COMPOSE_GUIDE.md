# ArtStore Docker Compose - Руководство по использованию

Полное руководство по запуску и управлению системой ArtStore через Docker Compose.

## Содержание

1. [Обзор файлов](#обзор-файлов)
2. [Быстрый старт](#быстрый-старт)
3. [Конфигурация окружения](#конфигурация-окружения)
4. [Сценарии использования](#сценарии-использования)
5. [Development Workflow](#development-workflow)
6. [Production Deployment](#production-deployment)
7. [Monitoring](#monitoring)
8. [Troubleshooting](#troubleshooting)
9. [Полезные команды](#полезные-команды)

---

## Обзор файлов

Проект использует модульную структуру Docker Compose файлов:

### 1. `docker-compose.infrastructure.yml`
**Назначение**: Базовая инфраструктура
- PostgreSQL 15 (async via asyncpg)
- Redis 7 (SYNC режим для Service Discovery!)
- MinIO (S3-compatible storage)
- PgAdmin (опционально)

**Когда использовать**: Всегда запускается первым, обязательна для всех сценариев

### 2. `docker-compose.backend.yml`
**Назначение**: Все backend микросервисы
- Admin Module (8000) - JWT auth, service accounts, saga orchestration
- Storage Element 01 (8010) - файловое хранилище
- Storage Element 02 (8011) - дополнительное хранилище (опционально, `--profile multi-storage`)
- Ingester Module (8020) - загрузка файлов
- Query Module (8030) - поиск и скачивание файлов

**Когда использовать**: Требует запущенную infrastructure

### 3. `docker-compose.dev.yml`
**Назначение**: Development override с hot-reload
- Text logging (удобнее читать в консоли)
- Монтирование source code для hot-reload
- Debug ports (5678-5682 для PyCharm/VS Code)
- БЕЗ persistent volumes (быстрая очистка)
- Single worker для упрощенного debugging

**Когда использовать**: Только для development, НИКОГДА в production!

### 4. `docker-compose.full.yml`
**Назначение**: All-in-one production стек
- Включает infrastructure + backend + monitoring
- Полностью автономный (не требует других файлов)
- Production-ready конфигурация

**Когда использовать**: Production-like окружение, быстрый старт, демонстрация

### 5. `docker-compose.monitoring.yml` (существующий)
**Назначение**: Observability stack
- Prometheus - сбор метрик
- Grafana - визуализация
- AlertManager - управление алертами
- Node Exporter - метрики хоста

**Когда использовать**: Добавляется к infrastructure + backend для мониторинга

---

## Быстрый старт

### Вариант А: Полный стек (самый простой)

```bash
# 1. Копируем и настраиваем environment
cp .env.example .env
# Редактируем .env (минимум: измените INITIAL_CLIENT_SECRET для production!)

# 2. Запускаем полный стек одной командой
docker-compose -f docker-compose.full.yml up -d

# 3. Проверяем статус
docker-compose -f docker-compose.full.yml ps

# 4. Смотрим логи
docker-compose -f docker-compose.full.yml logs -f
```

**Access URLs**:
- Admin API: http://localhost:8000
- Storage Element: http://localhost:8010
- Ingester API: http://localhost:8020
- Query API: http://localhost:8030
- PgAdmin: http://localhost:5050 (admin@admin.com / password)
- MinIO Console: http://localhost:9001 (minioadmin / minioadmin)
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin / admin123)

### Вариант Б: Модульный запуск (более гибкий)

```bash
# 1. Копируем environment
cp .env.example .env

# 2. Запускаем infrastructure
docker-compose -f docker-compose.infrastructure.yml up -d

# 3. Ждем готовности infrastructure (health checks)
docker-compose -f docker-compose.infrastructure.yml ps

# 4. Запускаем backend
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               up -d

# 5. Опционально: добавляем monitoring
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.monitoring.yml \
               up -d
```

---

## Конфигурация окружения

### Создание .env файла

```bash
cp .env.example .env
```

### Критически важные параметры для Production

**ОБЯЗАТЕЛЬНО изменить перед production деплоем:**

```bash
# .env
ENVIRONMENT=production

# Database credentials
DB_USERNAME=artstore
DB_PASSWORD=<STRONG_RANDOM_PASSWORD_32_CHARS>  # ⚠️ ИЗМЕНИТЬ!

# Redis (опционально, но рекомендуется)
REDIS_PASSWORD=<STRONG_RANDOM_PASSWORD_32_CHARS>  # ⚠️ НАСТРОИТЬ!

# MinIO S3 Storage
MINIO_ROOT_USER=<CUSTOM_USERNAME>  # ⚠️ ИЗМЕНИТЬ!
MINIO_ROOT_PASSWORD=<STRONG_RANDOM_PASSWORD_32_CHARS>  # ⚠️ ИЗМЕНИТЬ!

# Initial Admin Service Account
INITIAL_CLIENT_SECRET=<STRONG_RANDOM_PASSWORD_32_CHARS>  # ⚠️ ОБЯЗАТЕЛЬНО!

# CORS Configuration (CRITICAL!)
CORS_ALLOW_ORIGINS='["https://artstore.example.com","https://admin.artstore.example.com"]'  # ⚠️ Explicit domains!

# Grafana
GF_SECURITY_ADMIN_PASSWORD=<STRONG_PASSWORD>  # ⚠️ ИЗМЕНИТЬ!

# Logging (production)
LOG_LEVEL=INFO
LOG_FORMAT=json  # ОБЯЗАТЕЛЬНО json для production!
```

### Development параметры

```bash
# .env для development
ENVIRONMENT=development
LOG_LEVEL=DEBUG
LOG_FORMAT=text  # Только для dev!

# Development CORS
CORS_ALLOW_ORIGINS='["http://localhost:4200","http://localhost:8000","http://localhost:3000"]'
```

---

## Сценарии использования

### Сценарий 1: Development с hot-reload

```bash
# Полный development стек с hot-reload
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               up --build

# Логи в реальном времени (text формат, удобно для dev)
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               logs -f admin-module

# Быстрая очистка всех данных (БЕЗ persistent volumes в dev режиме)
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               down -v
```

**Преимущества dev режима**:
- Изменения кода сразу применяются (hot-reload)
- Text logging - удобнее читать
- Debug ports открыты (PyCharm/VS Code remote debugging)
- БЕЗ persistent data - быстрое тестирование и откат

### Сценарий 2: Production-like тестирование

```bash
# Полный production-like стек
docker-compose -f docker-compose.full.yml up -d

# Или модульно с мониторингом
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.monitoring.yml \
               up -d

# Логи в JSON формате (как в production)
docker-compose -f docker-compose.full.yml logs -f --tail=100
```

### Сценарий 3: Только infrastructure (для внешних модулей)

```bash
# Запуск только базовой инфраструктуры
docker-compose -f docker-compose.infrastructure.yml up -d

# Backend модули запускаются отдельно (не в Docker, например в IDE)
# Подключаются к localhost:5432 (postgres), localhost:6379 (redis), etc.
```

### Сценарий 4: Множественные Storage Elements

```bash
# Запуск с двумя storage-element
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               --profile multi-storage \
               up -d

# Storage Element 01: http://localhost:8010
# Storage Element 02: http://localhost:8011
```

---

## Development Workflow

### 1. Первый запуск проекта

```bash
# Клонирование и настройка
git clone <repository>
cd artStore

# Создание .env
cp .env.example .env
# Редактируем .env (можно оставить defaults для dev)

# Запуск infrastructure
docker-compose -f docker-compose.infrastructure.yml up -d

# Ожидание готовности (health checks)
docker-compose -f docker-compose.infrastructure.yml ps

# Запуск backend в dev режиме
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               up --build
```

### 2. Ежедневная разработка

```bash
# Утренний старт
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               up -d

# Работа с кодом (изменения применяются автоматически через hot-reload)
# Например: редактируем admin-module/app/api/endpoints/auth.py
# Сохраняем -> Uvicorn автоматически перезагружает -> готово!

# Просмотр логов конкретного модуля
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               logs -f admin-module

# Вечерняя остановка
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               down
# Данные сохраняются в infrastructure volumes
```

### 3. Remote Debugging (PyCharm / VS Code)

**VS Code**: `.vscode/launch.json`

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Attach to Admin Module",
      "type": "python",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/admin-module/app",
          "remoteRoot": "/app/app"
        }
      ]
    },
    {
      "name": "Python: Attach to Storage Element",
      "type": "python",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5679
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/storage-element/app",
          "remoteRoot": "/app/app"
        }
      ]
    }
  ]
}
```

**Debug ports**:
- Admin Module: 5678
- Storage Element 01: 5679
- Storage Element 02: 5680
- Ingester Module: 5681
- Query Module: 5682

### 4. Тестирование изменений

```bash
# Пересборка после изменений в Dockerfile или requirements.txt
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               up --build -d admin-module

# Перезапуск конкретного сервиса
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.dev.yml \
               restart admin-module

# Выполнение команд внутри контейнера
docker exec -it artstore_admin_module bash
# Внутри контейнера:
# py -m pytest tests/ -v
```

---

## Production Deployment

### 1. Pre-deployment Checklist

**КРИТИЧЕСКИ ВАЖНО перед production деплоем:**

- [ ] Скопировали `.env.example` в `.env`
- [ ] Изменили все пароли (DB, Redis, MinIO, Grafana)
- [ ] Установили `INITIAL_CLIENT_SECRET` (32+ chars random)
- [ ] Настроили `CORS_ALLOW_ORIGINS` (explicit domains, НЕ wildcard!)
- [ ] Установили `ENVIRONMENT=production`
- [ ] Проверили `LOG_FORMAT=json` (обязательно для production)
- [ ] Настроили backup стратегию для volumes
- [ ] Настроили TLS/SSL certificates (рекомендуется nginx reverse proxy)
- [ ] Настроили firewall rules
- [ ] Создали monitoring dashboards

### 2. Production Deployment

```bash
# 1. Подготовка окружения
cp .env.example .env
# Редактируем .env (ВСЕ критические параметры!)

# 2. Валидация конфигурации
docker-compose -f docker-compose.full.yml config

# 3. Запуск production стека
docker-compose -f docker-compose.full.yml up -d

# 4. Проверка health checks
docker-compose -f docker-compose.full.yml ps

# 5. Мониторинг логов (JSON формат)
docker-compose -f docker-compose.full.yml logs -f --tail=100
```

### 3. Production Updates (Rolling Updates)

```bash
# 1. Pull latest code
git pull origin main

# 2. Rebuild образы
docker-compose -f docker-compose.full.yml build

# 3. Graceful restart (по одному сервису)
docker-compose -f docker-compose.full.yml up -d --no-deps admin-module
# Ждем health check
docker-compose -f docker-compose.full.yml ps admin-module

docker-compose -f docker-compose.full.yml up -d --no-deps storage-element-01
# И так далее для каждого сервиса
```

### 4. Backup Strategy

```bash
# Backup PostgreSQL
docker exec artstore_postgres pg_dumpall -U artstore > backup_$(date +%Y%m%d).sql

# Backup Redis (если используется persistence)
docker exec artstore_redis redis-cli SAVE
docker cp artstore_redis:/data/dump.rdb ./backup/redis_$(date +%Y%m%d).rdb

# Backup MinIO data
docker exec artstore_minio mc mirror /data ./backup/minio_$(date +%Y%m%d)

# Backup volumes
docker run --rm -v artstore_postgres_data:/data -v $(pwd)/backup:/backup \
  alpine tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz /data
```

---

## Monitoring

### Доступ к Monitoring Tools

После запуска с monitoring:

```bash
docker-compose -f docker-compose.full.yml up -d
# Или
docker-compose -f docker-compose.infrastructure.yml \
               -f docker-compose.backend.yml \
               -f docker-compose.monitoring.yml \
               up -d
```

**Access URLs**:
- **Prometheus**: http://localhost:9090
  - Metrics от всех модулей на `/metrics`
  - PromQL queries для анализа

- **Grafana**: http://localhost:3000
  - Login: `admin` / `admin123` (изменить в production!)
  - Pre-configured dashboards в `monitoring/grafana/dashboards/`

- **AlertManager**: http://localhost:9093
  - Управление алертами
  - Routing rules

### Проверка метрик

```bash
# Метрики Admin Module
curl http://localhost:8000/metrics

# Метрики Storage Element
curl http://localhost:8010/metrics

# Метрики Ingester
curl http://localhost:8020/metrics

# Метрики Query Module
curl http://localhost:8030/metrics
```

### Добавление custom dashboards

1. Создайте JSON dashboard в Grafana UI
2. Export JSON
3. Сохраните в `monitoring/grafana/dashboards/`
4. Перезапустите Grafana:
   ```bash
   docker-compose -f docker-compose.full.yml restart grafana
   ```

---

## Troubleshooting

### Проблема: Сервис не запускается (unhealthy)

```bash
# 1. Проверяем статус
docker-compose -f docker-compose.full.yml ps

# 2. Смотрим логи проблемного сервиса
docker-compose -f docker-compose.full.yml logs admin-module

# 3. Проверяем health check вручную
docker exec artstore_admin_module curl -f http://localhost:8000/health/live

# 4. Заходим внутрь контейнера для debugging
docker exec -it artstore_admin_module bash
```

### Проблема: JWT ключи не найдены

**Симптомы**: Storage Element, Ingester, Query не могут валидировать JWT токены

```bash
# 1. Проверяем что Admin Module запустился и создал ключи
docker exec artstore_admin_module ls -la /app/.keys/

# 2. Проверяем что volume смонтирован в другие модули
docker exec artstore_storage_element_01 ls -la /app/.keys/

# 3. Если ключи не синхронизируются, копируем вручную
docker cp artstore_admin_module:/app/.keys/public_key.pem ./admin-module/.keys/
# Пересоздаем контейнеры
docker-compose -f docker-compose.backend.yml up -d --force-recreate
```

### Проблема: БД не инициализируется

```bash
# 1. Проверяем что init script выполнился
docker logs artstore_postgres | grep "init-databases.sh"

# 2. Заходим в PostgreSQL
docker exec -it artstore_postgres psql -U artstore -d artstore

# 3. Проверяем список БД
\l

# 4. Если БД нет, создаем вручную
CREATE DATABASE artstore_admin;
CREATE DATABASE artstore_storage_01;
-- и т.д.
```

### Проблема: Redis connection refused

```bash
# 1. Проверяем что Redis запущен
docker ps | grep redis

# 2. Проверяем health
docker exec artstore_redis redis-cli ping

# 3. Если password настроен, проверяем с auth
docker exec artstore_redis redis-cli -a ${REDIS_PASSWORD} ping

# 4. Проверяем что сервисы подключаются к правильному хосту
# Должно быть: redis (не localhost!)
docker logs artstore_admin_module | grep -i redis
```

### Проблема: Port already in use

```bash
# 1. Находим процесс занимающий порт (например 8000)
lsof -i :8000
# Или на Linux:
netstat -tulpn | grep 8000

# 2. Останавливаем процесс
kill -9 <PID>

# 3. Или меняем порт в .env
echo "ADMIN_MODULE_PORT=8001" >> .env

# 4. Обновляем docker-compose
docker-compose -f docker-compose.full.yml up -d
```

### Проблема: Out of disk space

```bash
# 1. Проверяем размер volumes
docker system df -v

# 2. Удаляем unused volumes
docker volume prune

# 3. Удаляем unused images
docker image prune -a

# 4. Полная очистка (ОСТОРОЖНО! Удалит все данные)
docker-compose -f docker-compose.full.yml down -v
docker system prune -a --volumes
```

### Проблема: Slow performance

```bash
# 1. Проверяем resource usage
docker stats

# 2. Увеличиваем resource limits в docker-compose.yml
# deploy:
#   resources:
#     limits:
#       cpus: '4.0'
#       memory: 4G

# 3. Проверяем PostgreSQL connection pool
# DB_POOL_SIZE=50  # увеличиваем в .env

# 4. Включаем Redis caching
# CACHE_REDIS_ENABLED=true
```

---

## Полезные команды

### Управление сервисами

```bash
# Запуск
docker-compose -f docker-compose.full.yml up -d

# Остановка
docker-compose -f docker-compose.full.yml down

# Перезапуск всех
docker-compose -f docker-compose.full.yml restart

# Перезапуск одного
docker-compose -f docker-compose.full.yml restart admin-module

# Просмотр статуса
docker-compose -f docker-compose.full.yml ps

# Масштабирование (несколько инстансов)
docker-compose -f docker-compose.full.yml up -d --scale storage-element-01=3
```

### Логи

```bash
# Все логи
docker-compose -f docker-compose.full.yml logs -f

# Конкретный сервис
docker-compose -f docker-compose.full.yml logs -f admin-module

# Последние 100 строк
docker-compose -f docker-compose.full.yml logs --tail=100

# С timestamp
docker-compose -f docker-compose.full.yml logs -f -t

# Поиск по логам
docker-compose -f docker-compose.full.yml logs admin-module | grep ERROR
```

### Выполнение команд

```bash
# Bash внутри контейнера
docker exec -it artstore_admin_module bash

# Python REPL
docker exec -it artstore_admin_module python

# Выполнение скрипта
docker exec artstore_admin_module python /app/scripts/test.py

# Database access
docker exec -it artstore_postgres psql -U artstore -d artstore_admin

# Redis CLI
docker exec -it artstore_redis redis-cli
```

### Очистка

```bash
# Остановка и удаление контейнеров
docker-compose -f docker-compose.full.yml down

# + удаление volumes (ВСЕ ДАННЫЕ!)
docker-compose -f docker-compose.full.yml down -v

# + удаление images
docker-compose -f docker-compose.full.yml down --rmi all

# Полная очистка системы (ОСТОРОЖНО!)
docker system prune -a --volumes
```

### Debugging

```bash
# Проверка конфигурации (без запуска)
docker-compose -f docker-compose.full.yml config

# Валидация docker-compose файла
docker-compose -f docker-compose.full.yml config --quiet

# Показать environment variables
docker-compose -f docker-compose.full.yml config | grep environment -A 20

# Inspect контейнера
docker inspect artstore_admin_module

# Top процессов
docker top artstore_admin_module

# Resource usage
docker stats artstore_admin_module
```

### Health Checks

```bash
# Проверка всех health checks
docker-compose -f docker-compose.full.yml ps

# Ручная проверка health endpoints
curl http://localhost:8000/health/live   # Admin
curl http://localhost:8000/health/ready  # Admin
curl http://localhost:8010/health/live   # Storage Element
curl http://localhost:8020/health/live   # Ingester
curl http://localhost:8030/health/ready  # Query
```

---

## Best Practices

### Development

1. **Всегда используйте dev override** для development:
   ```bash
   docker-compose -f docker-compose.infrastructure.yml \
                  -f docker-compose.backend.yml \
                  -f docker-compose.dev.yml \
                  up
   ```

2. **Используйте .env для secrets** (НЕ коммитьте в Git!)

3. **Регулярно чистите volumes** в dev режиме:
   ```bash
   docker-compose -f ... down -v
   ```

### Production

1. **ОБЯЗАТЕЛЬНО измените все пароли** перед деплоем

2. **Используйте external secrets management** (Docker Secrets, Vault, etc.)

3. **Настройте automated backups** для volumes

4. **Мониторинг health checks** и alerting через Prometheus/Grafana

5. **JSON logging** для интеграции с ELK/Splunk:
   ```bash
   LOG_FORMAT=json  # В .env
   ```

6. **Rolling updates** вместо полного рестарта

7. **Resource limits** для предотвращения OOM

---

## Дополнительные ресурсы

- **CLAUDE.md**: Полная документация проекта
- **monitoring/README.md**: Детальная документация по Prometheus/Grafana
- **DEVELOPMENT_PLAN.md**: План разработки и roadmap
- **SECURITY_SETUP.md**: Security best practices

---

## Поддержка

При возникновении проблем:

1. Проверьте секцию [Troubleshooting](#troubleshooting)
2. Смотрите логи: `docker-compose -f ... logs -f`
3. Проверьте health checks: `docker-compose -f ... ps`
4. Создайте issue в репозитории с описанием проблемы и логами
