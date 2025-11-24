# Структура проекта ArtStore

## Общая структура репозитория

```
/home/artur/Projects/artStore/
├── admin-module/           # Admin Module - центр управления и аутентификации
├── storage-element/        # Storage Element - физическое хранение файлов
├── ingester-module/        # Ingester Module - прием и загрузка файлов
├── query-module/           # Query Module - поиск и выдача файлов
├── admin-ui/               # Admin UI - Angular веб-интерфейс
├── scripts/                # Утилитные скрипты для разработки
├── images/                 # Изображения для документации
├── claudedocs/             # Документация для Claude Code
├── .serena/                # Serena MCP memories
├── .venv/                  # ЕДИНЫЙ Python virtual environment для всех модулей
├── docker-compose.yml      # Основной Docker Compose файл (ОБЯЗАТЕЛЬНО использовать!)
├── docker-compose.dev.yml  # Development конфигурация
├── docker-compose.monitoring.yml  # Мониторинг (Prometheus, Grafana)
├── README.md               # Главная документация проекта
├── DEVELOPMENT-GUIDE.md    # Руководство по разработке
└── CLAUDE.md               # Инструкции для Claude Code
```

## Структура Python модуля (типичная)

Все Python модули (admin-module, storage-element, ingester-module, query-module) следуют единой структуре:

```
<module-name>/
├── app/                    # Основной код приложения
│   ├── api/                # API endpoints
│   │   ├── dependencies/   # FastAPI dependencies (auth, etc.)
│   │   └── v1/             # API версия 1
│   │       └── endpoints/  # Endpoints по сущностям
│   ├── core/               # Конфигурация и ядро
│   │   ├── config.py       # Settings (Pydantic)
│   │   ├── database.py     # Database connection
│   │   ├── redis.py        # Redis connection
│   │   ├── logging_config.py  # Логирование
│   │   ├── metrics.py      # Prometheus metrics
│   │   └── observability.py   # OpenTelemetry
│   ├── db/                 # Database utilities
│   │   └── init_db.py      # Database initialization
│   ├── models/             # SQLAlchemy models
│   │   ├── base.py         # Base model
│   │   └── *.py            # Entity models
│   ├── schemas/            # Pydantic schemas (request/response)
│   │   └── *.py            # Schemas по сущностям
│   ├── services/           # Business logic
│   │   └── *_service.py    # Services по сущностям
│   ├── middleware/         # FastAPI middleware
│   │   ├── audit_middleware.py
│   │   └── rate_limit.py
│   ├── utils/              # Утилитные функции
│   └── main.py             # FastAPI application entrypoint
├── alembic/                # Database migrations
│   └── versions/           # Migration files
├── tests/                  # Тесты
│   ├── unit/               # Unit тесты
│   ├── integration/        # Integration тесты
│   └── conftest.py         # Pytest fixtures
├── Dockerfile              # Production Docker image
├── Dockerfile.dev          # Development Docker image
├── requirements.txt        # Python dependencies
├── pytest.ini              # Pytest конфигурация
├── alembic.ini             # Alembic конфигурация
├── config.yaml             # Application configuration
├── .env                    # Environment variables (НЕ в Git!)
├── .env.example            # Пример .env файла
├── .gitignore
└── README.md               # Документация модуля
```

## Ключевые файлы по модулям

### Admin Module (порты 8000-8009)

**Основные компоненты:**
```
admin-module/app/
├── api/v1/endpoints/
│   ├── auth.py             # OAuth 2.0 authentication
│   ├── admin_auth.py       # Admin user authentication
│   ├── service_accounts.py # Service Account management
│   ├── admin_users.py      # Admin user management
│   ├── storage_elements.py # Storage Element registry
│   ├── jwt_keys.py         # JWT key rotation
│   └── health.py           # Health checks
├── services/
│   ├── auth_service.py            # OAuth 2.0 logic
│   ├── admin_auth_service.py      # Admin authentication
│   ├── service_account_service.py # Service Account CRUD
│   ├── admin_user_service.py      # Admin user CRUD
│   ├── token_service.py           # JWT generation/validation
│   ├── jwt_key_rotation_service.py # Automatic key rotation
│   └── audit_service.py           # Audit logging
└── models/
    ├── service_account.py  # Service Account model
    ├── admin_user.py       # Admin user model
    ├── storage_element.py  # Storage Element registry
    ├── jwt_key.py          # JWT keys for rotation
    └── audit_log.py        # Audit log entries
```

### Storage Element (порты 8010-8019)

**Основные компоненты:**
```
storage-element/app/
├── api/v1/endpoints/
│   ├── files.py            # File operations (CRUD)
│   ├── health.py           # Health checks
│   └── admin.py            # Admin operations
├── services/
│   ├── file_service.py     # File management logic
│   ├── wal_service.py      # Write-Ahead Log
│   └── storage_service.py  # Physical storage operations
└── models/
    └── file_metadata.py    # File metadata model
```

**Критические компоненты:**
- `*.attr.json` файлы - источник истины для метаданных
- WAL (Write-Ahead Log) - атомарность операций
- Storage modes: edit, rw, ro, ar

### Ingester Module (порты 8020-8029)

**Основные компоненты:**
```
ingester-module/app/
├── api/v1/endpoints/
│   ├── upload.py           # File upload (streaming)
│   └── health.py
├── services/
│   ├── upload_service.py   # Upload logic
│   ├── validation_service.py # File validation
│   └── compression_service.py # Compression (Brotli/GZIP)
```

### Query Module (порты 8030-8039)

**Основные компоненты:**
```
query-module/app/
├── api/v1/endpoints/
│   ├── search.py           # File search
│   ├── download.py         # File download
│   └── health.py
├── services/
│   ├── search_service.py   # PostgreSQL Full-Text Search
│   ├── cache_service.py    # Multi-level caching
│   └── download_service.py # Resumable downloads
```

## Infrastructure Files

### Docker Compose

**Основной файл:** `/home/artur/Projects/artStore/docker-compose.yml`

**Сервисы:**
```yaml
services:
  # Infrastructure
  postgres         # PostgreSQL 15 (port 5432)
  redis            # Redis 7 (port 6379)
  minio            # MinIO S3-compatible storage (ports 9000, 9001)
  pgadmin          # PgAdmin web interface (port 5050)
  
  # Application Services
  admin-module     # Admin Module (port 8000)
  storage-element  # Storage Element (port 8010)
  ingester-module  # Ingester Module (port 8020)
  query-module     # Query Module (port 8030)
```

**Мониторинг:** `docker-compose.monitoring.yml`
```yaml
services:
  prometheus       # Metrics (port 9090)
  grafana          # Dashboards (port 3000)
  alertmanager     # Alerts (port 9093)
```

## Configuration Files

### Environment Variables

Каждый модуль имеет:
- `.env` - реальные credentials (в .gitignore)
- `.env.example` - шаблон с примерами

Основные переменные:
```bash
# Database
DB_HOST=postgres
DB_PORT=5432
DB_USERNAME=artstore
DB_PASSWORD=password
DB_NAME=artstore

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json  # json для production, text для development

# Security
JWT_PRIVATE_KEY_PATH=/path/to/private.pem
JWT_PUBLIC_KEY_PATH=/path/to/public.pem
```

### Config Files

- `config.yaml` - дополнительная конфигурация модуля
- `alembic.ini` - конфигурация миграций Alembic
- `pytest.ini` - конфигурация тестирования

## Testing Structure

```
<module>/tests/
├── unit/                   # Unit тесты
│   ├── test_services/
│   ├── test_models/
│   └── test_utils/
├── integration/            # Integration тесты
│   └── test_api/
├── conftest.py             # Pytest fixtures
└── __init__.py
```

## Documentation Structure

```
/home/artur/Projects/artStore/
├── README.md               # Главная документация
├── DEVELOPMENT-GUIDE.md    # Руководство по разработке
├── CLAUDE.md               # Инструкции для Claude Code
├── admin-module/README.md  # Документация Admin Module
├── storage-element/README.md  # Документация Storage Element
├── ingester-module/README.md  # Документация Ingester Module
└── query-module/README.md  # Документация Query Module
```

## Git Structure

### Branches
- `main` - основная ветка (production-ready)
- `feature/*` - feature branches для разработки
- `hotfix/*` - срочные исправления для production

### Git Workflow
1. Создать feature branch от main
2. Разработка и тестирование
3. Pull Request с code review
4. Merge в main после approval
5. Автоматический deployment

## Key Directories

- **Не использовать** docker-compose из поддиректорий модулей
- **Всегда** запускать Docker Compose из корня: `/home/artur/Projects/artStore/`
- **Единый .venv** для всех Python модулей в корне проекта
- **claudedocs/** - для отчетов Claude Code (не commits в Git)
- **.serena/** - Serena MCP memories (автоматически управляется)