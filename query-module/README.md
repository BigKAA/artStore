# Query Module - Поиск и скачивание файлов ArtStore

## Содержание

- [Назначение](#назначение)
- [Возможности](#возможности)
- [Быстрый старт](#быстрый-старт)
- [API Reference](#api-reference)
- [Архитектура](#архитектура)
  - [Search Engine](#search-engine)
  - [Caching Strategy](#caching-strategy)
  - [Download Service](#download-service)
  - [Event Subscriber](#event-subscriber)
- [Конфигурация](#конфигурация)
- [Мониторинг](#мониторинг)
- [Troubleshooting](#troubleshooting)

---

## Назначение

**Query Module** — сервис для поиска и получения файлов ArtStore:

- PostgreSQL Full-Text Search для поиска по метаданным
- Multi-level caching (Local → Redis) для минимизации latency
- Resumable downloads с HTTP Range requests
- JWT аутентификация
- Redis Pub/Sub для синхронизации кеша

---

## Возможности

| Функция | Статус | Описание |
|---------|--------|----------|
| Full-Text Search | ✅ | PostgreSQL GIN индексы |
| Partial Match | ✅ | LIKE queries |
| Exact Match | ✅ | Точное совпадение |
| Multi-level Cache | ✅ | Local (in-memory) + Redis |
| Resumable Downloads | ✅ | HTTP Range requests |
| Streaming Downloads | ✅ | Эффективная передача больших файлов |
| JWT Authentication | ✅ | RS256 с hot-reload публичного ключа |
| Cache Sync | ✅ | Redis Pub/Sub для инвалидации |
| Health Checks | ✅ | Liveness и Readiness probes |

---

## Быстрый старт

### Запуск через Docker Compose

```bash
# Из корня проекта
cd /home/artur/Projects/artStore
docker-compose up -d query-module
```

### Поиск файлов

```bash
# Получить токен
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "...", "client_secret": "..."}' | jq -r '.access_token')

# Поиск файлов
curl -X POST http://localhost:8030/api/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "contract", "mode": "partial"}'
```

### Проверка health

```bash
curl http://localhost:8030/health/ready | jq
```

---

## API Reference

Полная документация API: **[API.md](./API.md)**

### Основные endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/search` | POST | Поиск файлов с фильтрацией |
| `/api/search/{file_id}` | GET | Метаданные файла |
| `/api/download/{file_id}` | GET | Скачивание файла |
| `/api/download/{file_id}/metadata` | GET | Метаданные для скачивания |
| `/health/live` | GET | Liveness probe |
| `/health/ready` | GET | Readiness probe |

---

## Архитектура

### Search Engine

Поддерживает три режима поиска:

| Режим | Описание | Use Case |
|-------|----------|----------|
| `exact` | Точное совпадение | Поиск по UUID, hash |
| `partial` | LIKE queries | Поиск по части имени |
| `fulltext` | PostgreSQL FTS | Полнотекстовый поиск |

**Фильтры:**
- По имени файла, расширению, тегам
- По размеру (min/max)
- По дате создания
- По пользователю

**Сортировка:**
- `created_at`, `updated_at`, `file_size`, `filename`, `relevance`

### Caching Strategy

```
Request → Local Cache (LRU) → Redis Cache → PostgreSQL
```

| Уровень | TTL | Назначение |
|---------|-----|------------|
| Local (in-memory) | 60s | Горячие данные |
| Redis | 5min | Распределённый кеш |
| PostgreSQL | - | Source of truth |

**Инвалидация:**
- Redis Pub/Sub при обновлении файлов
- Автоматический TTL expiration

### Download Service

- **Streaming**: Эффективная передача больших файлов
- **Resumable**: HTTP Range requests для возобновления
- **Verification**: SHA256 checksum для проверки целостности

### Event Subscriber

Redis Pub/Sub подписка для синхронизации:
- Инвалидация кеша при изменениях
- Обновление метаданных файлов

---

## Конфигурация

### Основные переменные окружения

```bash
# Application
APP_NAME=ArtStore Query Module
APP_PORT=8030
APP_DEBUG=off
APP_SWAGGER_ENABLED=off

# Database (PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=artstore
DB_PASSWORD=password
DB_DATABASE=artstore

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=1

# JWT Authentication
AUTH_PUBLIC_KEY_PATH=/app/keys/public_key.pem

# Caching
LOCAL_CACHE_SIZE=1000
LOCAL_CACHE_TTL_SECONDS=60
REDIS_CACHE_TTL_SECONDS=300

# Search
SEARCH_DEFAULT_LIMIT=100
SEARCH_MAX_LIMIT=1000

# CORS
CORS_ENABLED=on
CORS_ALLOW_ORIGINS=http://localhost:4200

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Полный список переменных

См. [.env.example](./.env.example) для всех доступных параметров.

---

## Мониторинг

### Prometheus Metrics

Endpoint: `GET /metrics`

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Количество HTTP запросов |
| `http_request_duration_seconds` | Histogram | Latency запросов |

### Health Checks

| Endpoint | Назначение | Kubernetes |
|----------|------------|------------|
| `/health/live` | Приложение запущено | livenessProbe |
| `/health/ready` | Готов принимать трафик | readinessProbe |

### Критерии готовности

| Компонент | Критичность | Влияние |
|-----------|-------------|---------|
| PostgreSQL | Critical | 503 если недоступен |
| Redis | Optional | 200 с degraded status |

---

## Troubleshooting

### Медленный поиск

**Причина**: Отсутствуют GIN индексы или устаревшая статистика.

**Решение**:
```bash
# Проверить индексы
docker exec -it artstore_postgres psql -U artstore -c "\di"

# Обновить статистику
docker exec -it artstore_postgres psql -U artstore -c "ANALYZE file_metadata;"
```

### Low cache hit rate

**Причина**: Маленький размер кеша или короткий TTL.

**Решение**: Увеличить `LOCAL_CACHE_SIZE` и `REDIS_CACHE_TTL_SECONDS`.

### Storage Element unavailable

**Причина**: Storage Element недоступен для скачивания.

**Решение**:
```bash
# Проверить состояние SE
curl http://localhost:8010/health/live

# Проверить логи
docker-compose logs query-module
```

### JWT validation failed

**Причина**: Публичный ключ не синхронизирован.

**Решение**: Query Module поддерживает hot-reload JWT ключей. Проверьте что файл `public_key.pem` актуален.

---

## Ссылки

- [API Reference](./API.md)
- [Главная документация проекта](../README.md)
- [Admin Module](../admin-module/README.md)
- [Storage Element](../storage-element/README.md)
