# Admin Module - Центр управления и аутентификации ArtStore

## Содержание

- [Назначение](#назначение)
- [Возможности](#возможности)
- [Быстрый старт](#быстрый-старт)
- [API Reference](#api-reference)
- [Архитектура](#архитектура)
  - [Типы учетных записей](#типы-учетных-записей)
  - [JWT Authentication](#jwt-authentication)
  - [Health Checks](#health-checks)
  - [Garbage Collector](#garbage-collector)
- [Конфигурация](#конфигурация)
- [Мониторинг](#мониторинг)
- [Troubleshooting](#troubleshooting)

---

## Назначение

**Admin Module** — центр управления системой ArtStore:

- OAuth 2.0 аутентификация через Client Credentials flow
- Управление Service Accounts и Admin Users
- Service Discovery через публикацию в Redis
- Координация распределенных транзакций
- Garbage Collection для очистки файлов

---

## Возможности

| Функция | Статус | Описание |
|---------|--------|----------|
| OAuth 2.0 Authentication | ✅ | Client Credentials для Service Accounts |
| Admin Authentication | ✅ | Login/Password для администраторов |
| Service Accounts CRUD | ✅ | Создание, управление, ротация секретов |
| Admin Users CRUD | ✅ | Управление администраторами системы |
| Storage Elements | ✅ | Auto-discovery, синхронизация, health checks |
| JWT Key Rotation | ✅ | Автоматическая ротация ключей (24ч) |
| Service Discovery | ✅ | Публикация конфигурации в Redis |
| Garbage Collector | ✅ | Очистка TTL-expired и finalized файлов |
| File Registry | ✅ | Централизованный реестр файлов |
| Health Checks | ✅ | Liveness, Readiness, Startup probes |

---

## Быстрый старт

### Запуск через Docker Compose

```bash
# Из корня проекта
cd /home/artur/Projects/artStore
docker-compose up -d admin-module
```

### Получение токена (Service Account)

```bash
# Получить client_id и client_secret из логов при первом запуске
docker-compose logs admin-module | grep "client_id"

# Запросить токен
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "...", "client_secret": "..."}'
```

### Проверка health

```bash
curl http://localhost:8000/health/ready | jq
```

---

## API Reference

Полная документация API: **[API.md](./API.md)**

### Основные endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/auth/token` | POST | OAuth 2.0 токен для Service Accounts |
| `/api/v1/admin-auth/login` | POST | Вход для администраторов |
| `/api/v1/service-accounts/` | CRUD | Управление Service Accounts |
| `/api/v1/admin-users/` | CRUD | Управление Admin Users |
| `/api/v1/storage-elements/` | CRUD | Управление Storage Elements |
| `/api/v1/jwt-keys/` | GET/POST | Управление JWT ключами |
| `/api/v1/files/` | CRUD | File Registry |
| `/health/live` | GET | Liveness probe |
| `/health/ready` | GET | Readiness probe |

---

## Архитектура

### Типы учетных записей

#### Admin Users (H2M)

Администраторы системы с доступом к Admin UI.

| Атрибут | Описание |
|---------|----------|
| Username | Уникальный логин |
| Email | Уникальный email |
| Password | bcrypt hash (work factor 12) |
| Role | SUPER_ADMIN, ADMIN, READONLY |

**Аутентификация**: `POST /api/v1/admin-auth/login`

#### Service Accounts (M2M)

Machine-to-machine API доступ.

| Атрибут | Описание |
|---------|----------|
| Client ID | Автогенерация (формат: `sa_<env>_<name>_<random>`) |
| Client Secret | bcrypt hash, показывается только при создании |
| Role | ADMIN, USER, AUDITOR, READONLY |
| Status | ACTIVE, SUSPENDED, EXPIRED, DELETED |
| Rate Limit | По умолчанию 100 req/min |

**Аутентификация**: OAuth 2.0 через `POST /api/v1/auth/token`

### JWT Authentication

- **Алгоритм**: RS256 (asymmetric)
- **Access Token TTL**: 30 минут
- **Refresh Token TTL**: 7 дней
- **Key Rotation**: Автоматически каждые 24 часа

Публичный ключ доступен другим модулям для валидации токенов.

### Health Checks

#### Асинхронная архитектура

Readiness probe использует асинхронную проверку через APScheduler:

```
APScheduler (background) → HealthStateService (cache) → /health/ready (instant)
```

**Преимущества**:
- Мгновенный ответ (чтение из кеша)
- Нет нагрузки на БД/Redis при каждом запросе
- Стабильный response time

#### Критерии готовности

| Компонент | Критичность | Влияние |
|-----------|-------------|---------|
| PostgreSQL | Critical | 503 если недоступен |
| Таблицы БД | Critical | 503 если отсутствуют |
| Redis | Optional | 200 с warning |

### Garbage Collector

Фоновый сервис для автоматической очистки файлов.

#### Стратегии очистки

| Стратегия | Описание | Safety Margin |
|-----------|----------|---------------|
| TTL-based | Temporary файлы с истекшим TTL | Нет |
| Finalized | Файлы после финализации с Edit SE | 24 часа |
| Orphaned | Файлы без записей в БД | 7 дней |

#### Конфигурация

```bash
SCHEDULER_GC_ENABLED=true
SCHEDULER_GC_INTERVAL_HOURS=6
```

---

## Конфигурация

### Основные переменные окружения

```bash
# Application
APP_NAME=ArtStore Admin Module
APP_PORT=8000
APP_DEBUG=off
APP_SWAGGER_ENABLED=off

# Database (PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=artstore
DB_PASSWORD=password
DB_DATABASE=artstore_admin

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# JWT
JWT_ALGORITHM=RS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_KEY_ROTATION_HOURS=24

# Initial Admin User
INITIAL_ADMIN_ENABLED=on
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=ChangeMe123!
INITIAL_ADMIN_EMAIL=admin@artstore.local

# Initial Service Account
INITIAL_ACCOUNT_ENABLED=on
INITIAL_ACCOUNT_NAME=admin-service
INITIAL_ACCOUNT_ROLE=ADMIN

# Scheduler
SCHEDULER_ENABLED=on
SCHEDULER_JWT_ROTATION_ENABLED=on
SCHEDULER_GC_ENABLED=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Полный список переменных

См. [.env.example](./.env.example) для всех доступных параметров.

---

## Мониторинг

### Prometheus Metrics

Endpoint: `GET /health/metrics`

| Metric | Type | Description |
|--------|------|-------------|
| `admin_module_health_checks_total` | Counter | Количество health checks |
| `admin_module_database_status` | Gauge | Статус БД (1=up, 0=down) |
| `admin_module_redis_status` | Gauge | Статус Redis |
| `gc_files_cleaned_total` | Counter | Очищенные файлы GC |

### Health Checks

| Endpoint | Назначение | Kubernetes |
|----------|------------|------------|
| `/health/live` | Приложение запущено | livenessProbe |
| `/health/ready` | Готов принимать трафик | readinessProbe |
| `/health/startup` | Инициализация завершена | startupProbe |

---

## Troubleshooting

### Invalid JWT signature

**Причина**: Публичный ключ не синхронизирован между модулями.

**Решение**: Проверьте что все модули используют актуальный публичный ключ.

### Token expired

**Причина**: Access token живёт 30 минут.

**Решение**: Запросите новый токен через `POST /api/v1/auth/token`.

### Database connection failed

**Причина**: PostgreSQL недоступен или credentials неверные.

**Решение**:
```bash
# Проверить подключение
docker exec -it artstore_postgres psql -U artstore -d artstore_admin

# Проверить логи
docker-compose logs admin-module
```

### Redis connection timeout

**Причина**: Redis недоступен.

**Решение**: Service Discovery деградирует, модуль продолжит работу без Redis. Проверьте Redis:
```bash
docker exec -it artstore_redis redis-cli ping
```

---

## Ссылки

- [API Reference](./API.md)
- [Главная документация проекта](../README.md)
- [Ingester Module](../ingester-module/README.md)
- [Storage Element](../storage-element/README.md)
