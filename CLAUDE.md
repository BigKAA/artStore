# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ArtStore - это распределенная система файлового хранилища с микросервисной архитектурой, предназначенная для долгосрочного хранения документов с различными сроками хранения. Система реализует принципы отказоустойчивости, горизонтального масштабирования и обеспечивает разделение оперативного и архивного хранения.

## 📚 Документация проекта

**Для новой команды разработки**:
- **`README.md`** - Полное описание проекта, архитектура, технологии, roadmap
- **`DEVELOPMENT-GUIDE.md`** - Руководство по разработке, тестированию, Git workflow
- **Модульные README.md** - Детальное описание каждого модуля в их директориях

**Техническая документация**:
- **`README.md`** - Детальная техническая спецификация системы
- **`CLAUDE.md`** (этот файл) - Инструкции для AI-ассистента

## Общие правила работы

- **Честность**: Если не знаешь ответ - так и скажи. Не придумывай информацию.
- **Остановка при зацикливании**: Если выполнение задач зациклилось - остановись, спроси что делать дальше.
- **Комментарии**: Пиши подробные комментарии в коде на русском языке.
- **Язык общения**: Отвечай на русском языке.
- **Документация**: При вопросах по архитектуре/технологиям - читай `README.md` и `DEVELOPMENT-GUIDE.md` в первую очередь.

### 🔴 КРИТИЧЕСКОЕ: Конфигурационные параметры

**ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ**: Перед добавлением нового конфигурационного параметра в модуль:

1. **Проверь существующие параметры** - найди аналогичные по смыслу во ВСЕХ модулях
2. **Переиспользуй** - используй существующее имя и формат параметра
3. **Унифицируй** - если параметр используется в нескольких модулях, он должен иметь одинаковое имя и формат
4. **Документируй** - обнови `.env.example` и README.md с описанием параметра

**Анти-паттерн** (чего НЕ делать):
```bash
# ❌ НЕПРАВИЛЬНО: разные имена для одного смысла
STORAGE_MAX_SIZE_GB=10              # модуль A
STORAGE_S3_SOFT_CAPACITY_LIMIT=...  # модуль B
MAX_STORAGE_CAPACITY=10737418240    # модуль C
```

**Правильный подход**:
```bash
# ✅ ПРАВИЛЬНО: единый параметр во всех модулях
STORAGE_MAX_SIZE=10737418240  # в байтах, все модули
```

**Последствия нарушения**: Технический долг, сложность поддержки, необходимость масштабных рефакторингов для унификации.

### 🔴 КРИТИЧЕСКОЕ: Git Workflow

**ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ**: При выполнении любых задач, связанных с изменением файлов проекта, ВСЕГДА следовать Git Workflow.

**Полное описание см. `GIT-WORKFLOW-RULES.md`**

**Основные правила:**

1. **НИКОГДА не работать напрямую в main** - всегда создавать feature branch
2. **Branch naming**: `<type>/<short-description>`
   - `feature/` - новые features
   - `bugfix/` - исправления bugs
   - `docs/` - документация
   - `refactor/` - рефакторинг
   - `test/` - тесты
   - `hotfix/` - критические fixes

3. **Conventional Commits**: `<type>(<scope>): <subject>`
   ```bash
   feat(admin-module): Add OAuth2 authentication
   fix(storage): Fix WAL race condition
   docs: Update authentication guide
   refactor(ingester): Unify configuration parameters
   ```

4. **Workflow по завершении задачи:**
   - Создать commit с правильным форматом
   - Предложить выбор: локальный merge или GitHub PR
   - Удалить feature branch после merge

**Короткоживущие ветки** - merge как можно скорее (Trunk-Based Development)

## 🔴 КРИТИЧЕСКИ ВАЖНО: Docker Compose

**ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ №1**: Для запуска, тестирования и работы с проектом использовать ТОЛЬКО файлы `docker-compose*.yml` из **КОРНЯ ПРОЕКТА** (`/home/artur/Projects/artStore/`).

**ВСЕГДА**:
- ✅ `cd /home/artur/Projects/artStore` перед любыми docker-compose командами
- ✅ Использовать корневой `docker-compose.yml` для всех операций
- ✅ Запускать `docker-compose build [module-name]` из корня
- ✅ Запускать `docker-compose up -d [module-name]` из корня

**НИКОГДА**:
- ❌ НЕ создавать и не использовать docker-compose в/из поддиректорий (admin-module/, ingester-module/, etc.)
- ❌ НЕ создавать собственные docker-compose файлы для модулей
- ❌ НЕ запускать модули напрямую без Docker

## 🔐 Автозагрузка: Аутентификация

**При загрузке проекта (`/sc:load`) ОБЯЗАТЕЛЬНО загрузи память `authentication_quick_start`**:
```
read_memory("authentication_quick_start")
```

Эта память содержит:
- Быстрые команды получения токена
- Актуальные credentials из docker-compose.yml
- Примеры использования API всех модулей

## Быстрый старт

**Подробнее см. `DEVELOPMENT-GUIDE.md`**

### Инфраструктура

**Базовые компоненты** (запускаются через `docker-compose.yml`):
- **PostgreSQL** (port 5432) - основная БД
- **Redis** (port 6379) - Service Discovery и кеширование
- **MinIO** (ports 9000/9001) - S3-совместимое хранилище
- **PgAdmin** (port 5050) - веб-интерфейс для PostgreSQL

**Credentials**: См. `docker-compose.yml` для логинов/паролей всех сервисов.

**Database operations**: Используй инструменты внутри контейнера postgres. Создавай базы данных по необходимости.

**Authentication**: Только OAuth 2.0 Client Credentials.

### Запуск окружения

```bash
cd /home/artur/Projects/artStore

# Запуск инфраструктуры + все модули
docker-compose up -d

# Просмотр логов
docker-compose logs -f [module-name]

# Пересборка модуля
docker-compose build [module-name]
docker-compose up -d [module-name]

# Остановка
docker-compose down

# Мониторинг (опционально)
docker-compose -f docker-compose.monitoring.yml up -d
```

### Python Virtual Environment

**ЕДИНЫЙ .venv для всех Python модулей**: `/home/artur/Projects/artStore/.venv`

```bash
# Создание (один раз)
python3 -m venv .venv

# Активация
source .venv/bin/activate

# Установка зависимостей всех модулей
pip install -r admin-module/requirements.txt
pip install -r storage-element/requirements.txt
pip install -r ingester-module/requirements.txt
pip install -r query-module/requirements.txt
```

### Service Ports

- **Infrastructure**: PostgreSQL: 5432, PgAdmin: 5050, Redis: 6379, MinIO: 9000/9001
- **Modules**: Admin Module: 8000-8009, Storage: 8010-8019, Ingester: 8020-8029, Query: 8030-8039, UI: 4200

## Ключевые архитектурные принципы

**Для детального понимания см. `README.md`**

### Критически важные концепции

1. **Attribute-First Storage Model**: Файлы `*.attr.json` - единственный источник истины для метаданных
2. **JWT RS256 Authentication**: Центральная аутентификация через Admin Module с публичным ключом
3. **Redis ASYNC Mode**: Все модули используют **асинхронный** `redis.asyncio` (НЕ синхронный redis-py) для Service Discovery и кеширования
4. **PostgreSQL ASYNC**: Database операции через asyncpg
5. **WAL Protocol**: Write-Ahead Log для атомарности операций с файлами
6. **Saga Pattern**: Координация распределенных транзакций через Admin Module
7. **Circuit Breaker**: Graceful degradation при недоступности dependencies

### Service Discovery Pattern (Sprint 16)

- Admin Module публикует конфигурацию storage-elements в Redis
- Ingester/Query подписываются на обновления через Redis Pub/Sub
- **Fallback chain**: Redis → Admin Module API → Error (НЕТ статического fallback)
- **ВАЖНО (Sprint 16)**: `STORAGE_ELEMENT_BASE_URL` удалён, Service Discovery обязателен

### Redis Async Usage Pattern

**КРИТИЧЕСКИ ВАЖНО**: Все модули используют **асинхронный** `redis.asyncio`, а НЕ синхронный `redis-py`.

**Правильная реализация** (см. `admin-module/app/core/redis.py`):

```python
import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

# Создание async client
async def get_redis() -> Redis:
    client = await aioredis.from_url(
        settings.redis.url,
        max_connections=settings.redis.pool_size,
        decode_responses=True
    )
    return client

# Использование в FastAPI endpoints
@app.get("/cache")
async def get_cache():
    redis_client = await get_redis()
    value = await redis_client.get("key")  # await обязателен!
    return {"value": value}

# Service Discovery через Pub/Sub
async def subscribe_to_updates():
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    async for message in pubsub.listen():
        if message["type"] == "message":
            await handle_update(message["data"])
```

**Примеры операций**:
- `await redis.get(key)` - чтение
- `await redis.set(key, value, ex=3600)` - запись с TTL
- `await redis.publish(channel, message)` - публикация
- `async for msg in pubsub.listen()` - подписка

## Архитектура модулей

**Детальное описание каждого модуля см. в их README.md**

### Модули системы

1. **Admin Module** (порты 8000-8009) - Аутентификация и управление
   - OAuth 2.0 JWT (RS256), Service Accounts, Saga координация
   - См. `admin-module/README.md`

2. **Storage Element** (порты 8010-8019) - Физическое хранение файлов
   - Режимы: edit, rw, ro, ar (см. раздел "Конфигурация")
   - WAL protocol, attr.json файлы
   - См. `storage-element/README.md`

3. **Ingester Module** (порты 8020-8029) - Загрузка файлов
   - Streaming upload, validation, compression
   - Service Discovery обязателен (Sprint 16)
   - Health endpoints: `/health/live`, `/health/ready`
   - См. `ingester-module/README.md`

4. **Query Module** (порты 8030-8039) - Поиск и скачивание
   - PostgreSQL Full-Text Search, multi-level caching
   - См. `query-module/README.md`

5. **Admin UI** (порт 4200) - Angular веб-интерфейс
   - Dashboard, управление аккаунтами, file manager
   - См. `admin-ui/README.md`

## Конфигурация

### Configuration Priority

**Environment variables > config files**

Все модули приоритизируют переменные окружения над значениями в конфигурационных файлах. Примеры конфигураций см. в модульных README.md

### Storage Element Modes

- **edit**: Full CRUD (не меняется через API)
- **rw**: Read-write без deletion (переход в ro через API)
- **ro**: Read-only (переход в ar через API)
- **ar**: Archive mode (только через конфиг + restart)

### Логирование

**Production**: JSON формат ОБЯЗАТЕЛЕН (`LOG_FORMAT=json`)
**Development**: Text формат разрешен (`LOG_FORMAT=text`)

### Унифицированные параметры конфигурации

Все модули используют единую конвенцию именования параметров:

```bash
# Database (все модули с БД)
DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_DATABASE
DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_ECHO
DB_SSL_ENABLED, DB_SSL_MODE, DB_SSL_CA_CERT

# Swagger (все модули)
APP_SWAGGER_ENABLED=on|off

# Logging (все модули)
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR|CRITICAL
LOG_FORMAT=json|text

# Redis (все модули)
REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
# DB allocation: 0=Admin/Storage/Ingester, 1=Query

# Storage (storage-element)
STORAGE_MAX_SIZE=<bytes>  # Например: 10737418240 (10GB)
```

## Основные команды

**Полное руководство см. `DEVELOPMENT-GUIDE.md`**

### Тестирование

```bash
# Активировать venv
source .venv/bin/activate

# Запуск тестов модуля
cd [module-name]
pytest tests/ -v

# С coverage
pytest tests/ --cov=app --cov-report=html
```

### Database

```bash
# Подключение к PostgreSQL
docker exec -it artstore_postgres psql -U artstore -d artstore

# Создание новой БД
docker exec -it artstore_postgres createdb -U artstore [db_name]
```

## Credentials & Authentication

### Initial Service Account

Автоматически создается при первом запуске (если включено `INITIAL_ACCOUNT_ENABLED=true`):

**Конфигурация через Environment Variables**:
- `INITIAL_ACCOUNT_ENABLED` - включить/выключить автоматическое создание (default: true)
- `INITIAL_ACCOUNT_NAME` - название Service Account (default: "admin-service")
- `INITIAL_ACCOUNT_ROLE` - роль: ADMIN/USER/AUDITOR/READONLY (default: ADMIN)
- `INITIAL_ACCOUNT_PASSWORD` - client_secret (если не задан → автогенерация)

**Поведение**:
- Если `INITIAL_ACCOUNT_PASSWORD` **не задан**: client_secret автоматически генерируется, сохраняется в БД в зашифрованном виде (bcrypt), а plain text secret выводится в логи **ОДИН РАЗ** при создании
- Если `INITIAL_ACCOUNT_PASSWORD` **задан**: используется указанный пароль
- Если Service Account с таким именем **уже существует**: ничего не делается (идемпотентность)

**Характеристики**:
- Name: `admin-service` (или из `INITIAL_ACCOUNT_NAME`)
- Role: `ADMIN` (или из `INITIAL_ACCOUNT_ROLE`)
- Client ID: Автоматическая генерация (формат: `sa_prod_<name>_<random>`)
- Client Secret: Bcrypt хеш (work factor 12)
- Rate Limit: 1000 req/min (повышенный лимит для системного аккаунта)
- Secret Expiration: 90 дней
- **ВАЖНО**: `is_system=True` - не удаляется через API

**PRODUCTION Security**:
- ✅ **Обязательно установить** `INITIAL_ACCOUNT_PASSWORD` через `.env` или environment variable
- ✅ **Никогда не использовать** автогенерированный пароль в production
- ✅ **Сразу после деплоя** проверить логи для получения credentials (если автогенерация)
- ✅ **Хранить credentials** в защищенном секретном хранилище (Vault, AWS Secrets Manager)
- ⚠️ **Минимальная длина пароля**: 12 символов

**Пример конфигурации** (`.env` или `docker-compose.yml`):
```bash
INITIAL_ACCOUNT_ENABLED=true
INITIAL_ACCOUNT_NAME=admin-service
INITIAL_ACCOUNT_PASSWORD=YourSecurePasswordHere123!  # Production: обязательно задать!
INITIAL_ACCOUNT_ROLE=ADMIN
```

### OAuth 2.0 пример

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "...", "client_secret": "..."}'
```

### Infrastructure Credentials

См. `docker-compose.yml`:
- PostgreSQL: artstore / password
- PgAdmin: admin@admin.com / password
- MinIO: minioadmin / minioadmin

## Критические требования реализации

**Полный список см. `README.md` → "Критические требования"**

### Важнейшие правила

1. **Consistency Protocol**: WAL → Attr File → DB Cache → Service Discovery → Commit (строго в порядке)
2. **Attribute Files First**: Всегда сначала запись в `*.attr.json`, затем в DB cache
3. **Stateless Design**: Все модули должны быть stateless
4. **Circuit Breaker**: Обязателен для всех inter-service communications
5. **Configuration Reuse**: Перед добавлением новых параметров - проверь и переиспользуй существующие (см. раздел "Общие правила работы")

## Мониторинг

### Быстрый старт

```bash
# Запуск мониторинга
docker-compose -f docker-compose.monitoring.yml up -d

# Доступ к интерфейсам
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin / admin123)
# AlertManager: http://localhost:9093
```

### Компоненты

- **OpenTelemetry**: Distributed tracing во всех модулях
- **Prometheus**: Метрики на `/metrics` каждого модуля
- **Grafana**: Pre-configured dashboards
- **AlertManager**: Critical/Warning alerts
- **Health Checks**: `/health/live` и `/health/ready` на всех модулях

## Безопасность

**Полные требования см. `README.md` → "Security Framework"**

### Ключевые принципы

1. **JWT RS256**: Access tokens (30 min), автоматическая ротация ключей (24ч)
2. **Bearer Authentication**: Обязательна для всех API (кроме /health)
3. **Audit Logging**: Все операции с tamper-proof signatures
4. **Rate Limiting**: Adaptive limiting с автоблокировкой
5. **RBAC**: Fine-grained resource-level permissions

### Production Checklist

- [ ] Изменить все default credentials в `.env`
- [ ] Включить audit logging
- [ ] Настроить rate limiting
- [ ] Проверить CORS политики
- [ ] Включить automated vulnerability scanning
