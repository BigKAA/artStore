# Ingester Module

Сервис приёма и управления файлами для системы ArtStore.

---

## Содержание

- [Назначение](#назначение)
- [Возможности](#возможности)
- [Быстрый старт](#быстрый-старт)
- [API Reference](#api-reference)
- [Архитектура](#архитектура)
  - [Storage Element Selection](#storage-element-selection)
  - [Retention Policy](#retention-policy)
  - [Service Discovery](#service-discovery)
  - [Capacity Monitor](#capacity-monitor)
- [Конфигурация](#конфигурация)
- [Мониторинг](#мониторинг)
- [Troubleshooting](#troubleshooting)

---

## Назначение

**Ingester Module** — сервис для загрузки файлов в распределенное хранилище ArtStore:

- Приём файлов через REST API
- Автоматический выбор Storage Element
- Поддержка Retention Policy (temporary/permanent)
- Two-Phase Commit финализация файлов
- Интеграция с Service Discovery

---

## Возможности

| Функция | Статус | Описание |
|---------|--------|----------|
| File Upload | ✅ | Загрузка файлов с multipart/form-data |
| Retention Policy | ✅ | temporary (Edit SE) / permanent (RW SE) |
| File Finalization | ✅ | Two-Phase Commit перенос temporary → permanent |
| Service Discovery | ✅ | Динамический выбор SE через Redis/Admin Module |
| Capacity Monitor | ✅ | Polling capacity метрик с Leader Election |
| Compression | ✅ | gzip/brotli сжатие при загрузке |
| Health Checks | ✅ | Liveness и Readiness probes |

---

## Быстрый старт

### Запуск через Docker Compose

```bash
# Из корня проекта
cd /home/artur/Projects/artStore
docker-compose up -d ingester-module
```

### Загрузка файла

```bash
# Получить токен
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "...", "client_secret": "..."}' | jq -r '.access_token')

# Загрузить файл
curl -X POST http://localhost:8020/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf" \
  -F "retention_policy=temporary"
```

### Проверка health

```bash
curl http://localhost:8020/health/ready | jq
```

---

## API Reference

Полная документация API: **[API.md](./API.md)**

### Основные endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/files/upload` | POST | Загрузка файла |
| `/api/v1/finalize/{file_id}` | POST | Финализация temporary файла |
| `/api/v1/finalize/{transaction_id}/status` | GET | Статус финализации |
| `/health/live` | GET | Liveness probe |
| `/health/ready` | GET | Readiness probe |

---

## Архитектура

### Storage Element Selection

Ingester автоматически выбирает Storage Element для загрузки на основе:
- **Retention Policy**: temporary → Edit SE, permanent → RW SE
- **Capacity**: SE с достаточным свободным местом
- **Priority**: Порядок приоритета из конфигурации
- **Health**: Только healthy SE

```
┌─────────────────────────────────────────────────────┐
│              StorageSelector Flow                    │
├─────────────────────────────────────────────────────┤
│  1. Определить required_mode из retention_policy    │
│     TEMPORARY → edit | PERMANENT → rw               │
│                                                      │
│  2. Получить SE из Redis Registry                   │
│     - Проверить capacity_status != FULL             │
│     - Проверить can_accept_file(file_size)          │
│                                                      │
│  3. Fallback: Admin Module API                      │
│     GET /api/v1/internal/storage-elements/available │
│                                                      │
│  4. Return StorageElementInfo или 503 Error         │
└─────────────────────────────────────────────────────┘
```

### Retention Policy

| Policy | Target SE | TTL | Use Case |
|--------|-----------|-----|----------|
| `temporary` | Edit | 1-365 дней (default: 30) | Документы в работе, drafts |
| `permanent` | RW | Нет | Финализированные документы |

**Workflow temporary файлов:**
1. Upload с `retention_policy=temporary` → файл в Edit SE
2. Работа над документом
3. `POST /finalize/{file_id}` → Two-Phase Commit → файл в RW SE
4. Оригинал удаляется через GC (+24h safety margin)

### Service Discovery

Ingester получает информацию о Storage Elements через:

1. **Redis Registry** (primary) — real-time данные
2. **Admin Module API** (fallback) — cached данные из БД

```
Fallback Chain: Redis → Admin Module → 503 Error
```

> ⚠️ Service Discovery обязателен. Статическая конфигурация SE не поддерживается.

### Capacity Monitor

**AdaptiveCapacityMonitor** — сервис для мониторинга capacity Storage Elements:

- **Leader Election**: Только 1 Ingester (Leader) выполняет polling
- **HTTP Polling**: GET `/api/v1/capacity` к каждому SE
- **Redis Cache**: Shared cache для всех Ingester instances
- **Adaptive Intervals**: Автоматическая настройка интервала polling
- **Dynamic Reload**: Автоматическое обнаружение новых SE (каждые 60s)

---

## Конфигурация

### Environment Variables

```bash
# Application
APP_NAME=artstore-ingester
APP_PORT=8020
APP_DEBUG=off
APP_SWAGGER_ENABLED=off

# Authentication
AUTH_ENABLED=on
AUTH_PUBLIC_KEY_PATH=/app/keys/public_key.pem
AUTH_ADMIN_MODULE_URL=http://admin-module:8000

# Service Account (для M2M аутентификации)
SERVICE_ACCOUNT_CLIENT_ID=sa_prod_ingester_...
SERVICE_ACCOUNT_CLIENT_SECRET=<secret>
SERVICE_ACCOUNT_ADMIN_MODULE_URL=http://admin-module:8000

# Redis (Service Discovery)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Storage Element HTTP Client
STORAGE_ELEMENT_TIMEOUT=30
STORAGE_ELEMENT_MAX_RETRIES=3

# Compression
COMPRESSION_ENABLED=on
COMPRESSION_ALGORITHM=gzip
COMPRESSION_LEVEL=6

# Capacity Monitor
CAPACITY_MONITOR_ENABLED=on
CAPACITY_MONITOR_BASE_INTERVAL=30
CAPACITY_MONITOR_CONFIG_RELOAD_INTERVAL=60

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
| `artstore_ingester_uploads_total` | Counter | Количество загрузок |
| `artstore_ingester_upload_duration_seconds` | Histogram | Latency загрузки |
| `artstore_ingester_upload_size_bytes` | Histogram | Размер файлов |
| `ingester_se_config_reload_total` | Counter | Config reload attempts |
| `ingester_se_endpoints_count` | Gauge | Количество известных SE |

### Health Checks

| Endpoint | Назначение | Kubernetes |
|----------|------------|------------|
| `/health/live` | Приложение запущено | livenessProbe |
| `/health/ready` | Готов принимать трафик | readinessProbe |

---

## Troubleshooting

### 503 Service Unavailable - No available Storage Elements

**Причина:** Service Discovery не может найти доступные SE

**Решение:**
```bash
# 1. Проверить Redis
redis-cli ping

# 2. Проверить Admin Module
curl http://admin-module:8000/health/live

# 3. Проверить SE в Redis
redis-cli KEYS "storage:*"

# 4. Проверить логи Ingester
docker-compose logs -f ingester-module
```

### RuntimeError: StorageSelector is required

**Причина:** StorageSelector не инициализирован

**Решение:**
1. Проверить `AUTH_ADMIN_MODULE_URL`
2. Проверить сетевую связность
3. Дождаться полного старта Admin Module

### Upload timeout

**Причина:** Медленное соединение с Storage Element

**Решение:**
- Увеличить `STORAGE_ELEMENT_TIMEOUT`
- Проверить network latency к SE

### High memory usage

**Причина:** Большие файлы в памяти

**Решение:**
- Проверить streaming upload implementation
- Уменьшить concurrent uploads

---

## Ссылки

- [API Reference](./API.md)
- [Главная документация проекта](../README.md)
- [Admin Module](../admin-module/README.md)
- [Storage Element](../storage-element/README.md)
