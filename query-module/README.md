# Query Module - File Search and Download Service

Микросервис для поиска и скачивания файлов в распределенной системе ArtStore.

## Ключевые возможности

### Search Features
- **PostgreSQL Full-Text Search** с GIN индексами для мгновенного поиска
- **Multi-Level Caching**: Local (in-memory) → Redis → PostgreSQL
- **Search Modes**: Exact, Partial (LIKE), Full-Text (ts_query)
- **Фильтрация**: по тегам, размеру, дате, пользователю, MIME типу
- **Пагинация и сортировка**

### Download Features
- **Streaming Downloads** для больших файлов
- **Resumable Downloads** через HTTP Range requests
- **SHA256 Verification** после скачивания
- **Connection Pooling** HTTP/2 для оптимальной производительности
- **Download Statistics** для мониторинга и analytics

### Architecture
- **Async PostgreSQL** (asyncpg + SQLAlchemy)
- **Sync Redis** (redis-py, согласно архитектурным требованиям)
- **JWT RS256 Authentication** через публичный ключ Admin Module
- **JSON Structured Logging** (обязательно для production)
- **Prometheus Metrics** для мониторинга
- **Health Checks** для Kubernetes

## Quick Start

### Prerequisites
- Docker и Docker Compose
- PostgreSQL 15+ (или используйте docker-compose)
- Redis 7+ (или используйте docker-compose)
- JWT public key от Admin Module

### Запуск с Docker Compose

```bash
# 1. Копирование .env файла
cp .env.example .env

# 2. Настройка environment variables в .env
vim .env

# 3. Запуск всех сервисов
docker-compose up -d

# 4. Применение database миграций
docker-compose exec query-module alembic upgrade head

# 5. Проверка health
curl http://localhost:8030/health/ready
```

### Development Mode

```bash
# 1. Создание virtual environment (глобальный venv в корне проекта)
cd /path/to/artStore
python3 -m venv .venv
source .venv/bin/activate

# 2. Установка зависимостей
pip install -r query-module/requirements.txt

# 3. Настройка .env
cd query-module
cp .env.example .env

# 4. Запуск базовых сервисов (PostgreSQL, Redis)
docker-compose up -d postgres redis

# 5. Применение миграций
alembic upgrade head

# 6. Запуск приложения
python -m app.main
```

## API Endpoints

### Search API
- `POST /api/search` - Поиск файлов с фильтрацией
- `GET /api/search/{file_id}` - Получение метаданных файла

### Download API
- `GET /api/download/{file_id}/metadata` - Метаданные для скачивания
- `GET /api/download/{file_id}` - Скачивание файла (с поддержкой Range)

### System API
- `GET /health/live` - Liveness check (Kubernetes)
- `GET /health/ready` - Readiness check (Kubernetes)
- `GET /metrics` - Prometheus metrics
- `GET /docs` - Swagger UI documentation

## Configuration

Все настройки через environment variables (см. `.env.example`).

### Критические настройки

**Database**:
- `DATABASE_URL` - PostgreSQL connection string
- `DATABASE_POOL_SIZE` - Размер connection pool (default: 20)

**Redis** (SYNC режим):
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`
- `REDIS_MAX_CONNECTIONS` - Connection pool size

**Cache**:
- `CACHE_LOCAL_TTL` - Local cache TTL (default: 300s)
- `CACHE_REDIS_TTL` - Redis cache TTL (default: 1800s)

**Authentication**:
- `AUTH_PUBLIC_KEY_PATH` - Путь к JWT public key от Admin Module

**Logging**:
- `LOG_FORMAT=json` - **ОБЯЗАТЕЛЬНО** для production

## Database Migrations

```bash
# Создание новой миграции
alembic revision --autogenerate -m "description"

# Применение миграций
alembic upgrade head

# Откат миграции
alembic downgrade -1
```

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (требуется docker-compose)
pytest tests/integration/ -v

# Coverage
pytest --cov=app --cov-report=html
```

## Monitoring

### Prometheus Metrics
- `http://localhost:8030/metrics` - Endpoint для Prometheus scraping

### Health Checks
- `GET /health/live` - Проверка живости процесса
- `GET /health/ready` - Проверка готовности (DB + Cache)

### Logs
- **Production**: JSON формат для ELK Stack, Splunk
- **Development**: Text формат для удобства отладки

## Architecture Notes

### Multi-Level Caching Strategy
1. **Local Cache** (in-memory): 300s TTL, fastest
2. **Redis Cache**: 1800s TTL, distributed
3. **PostgreSQL**: Source of truth, fallback

### PostgreSQL Full-Text Search
- GIN индексы на `search_vector` (ts_vector)
- Автоматическое обновление через trigger
- Поддержка русского языка (russian config)

### SYNC Redis
**ВАЖНО**: Redis используется в SYNC режиме (redis-py) согласно архитектурным требованиям ArtStore проекта.

## Troubleshooting

### Database connection failed
```bash
# Проверка PostgreSQL доступности
docker-compose exec postgres pg_isready -U artstore
```

### Redis unavailable
```bash
# Проверка Redis
docker-compose exec redis redis-cli ping
```

### JWT validation failed
```bash
# Проверка наличия public key
ls -la ../admin-module/keys/public_key.pem
```

## Security

- **JWT RS256 Authentication** для всех API endpoints (кроме health checks)
- **Non-root Docker user** для безопасности контейнера
- **SHA256 Verification** для целостности скачанных файлов
- **TLS 1.3** для production deployment (настраивается на reverse proxy)

## Performance

- **Connection Pooling**: HTTP/2 persistent connections
- **Streaming Downloads**: Минимизация memory usage
- **Multi-Level Caching**: Снижение нагрузки на БД
- **Async I/O**: Высокая concurrency для PostgreSQL

## License

Proprietary - ArtStore Project
