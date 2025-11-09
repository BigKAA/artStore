# ArtStore - Структура кодовой базы

## Корневая структура проекта

```
artStore/
├── admin-module/              # Admin Module Cluster (порты 8000-8009)
│   └── README.md
├── storage-element/           # Storage Element (порты 8010-8019)
│   ├── alembic/               # Database migrations
│   ├── app/                   # Основное приложение
│   │   ├── db/                # Database connections
│   │   ├── api/               # REST API endpoints
│   │   ├── services/          # Business logic
│   │   ├── utils/             # Utilities
│   │   ├── models/            # SQLAlchemy models
│   │   └── core/              # Configuration, security
│   ├── tests/                 # Unit и integration тесты
│   ├── images/                # Документация с картинками
│   └── README.md
├── ingester-module/           # Ingester Cluster (порты 8020-8029)
│   └── README.md
├── query-module/              # Query Cluster (порты 8030-8039)
│   └── README.md
├── admin-ui/                  # Angular Admin UI (порт 4200)
│   └── README.md
├── images/                    # Общие изображения для документации
├── .archive/                  # Архивные документы
├── .utils/                    # Утилиты и вспомогательные скрипты
│   └── dex/                   # Конфигурация Dex OIDC
├── docker-compose.yml         # ✅ Базовая инфраструктура
├── CLAUDE.md                  # Инструкции для Claude Code
├── README.md                  # Главная документация
├── DEVELOPMENT_PLAN.md        # План разработки
├── ARCHITECTURE_DECISIONS.md # Архитектурные решения
├── AGENTS.md                  # Информация об агентах
└── .gitignore
```

## Детальная структура модуля (на примере storage-element)

```
storage-element/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI приложение, точка входа
│   │
│   ├── core/                      # Ядро приложения
│   │   ├── __init__.py
│   │   ├── config.py              # Конфигурация (Pydantic Settings)
│   │   ├── security.py            # JWT валидация, RBAC
│   │   ├── logging.py             # Настройка логирования
│   │   └── exceptions.py          # Кастомные исключения
│   │
│   ├── api/                       # REST API
│   │   ├── __init__.py
│   │   ├── deps.py                # Зависимости FastAPI (get_db, get_current_user)
│   │   └── v1/                    # API версия 1
│   │       ├── __init__.py
│   │       ├── router.py          # Главный router
│   │       └── endpoints/         # Endpoints по ресурсам
│   │           ├── files.py       # Файловые операции
│   │           ├── admin.py       # Административные endpoints
│   │           ├── health.py      # Health checks
│   │           └── metrics.py     # Prometheus metrics
│   │
│   ├── models/                    # SQLAlchemy ORM модели
│   │   ├── __init__.py
│   │   ├── file.py                # Модель файла (cache)
│   │   ├── storage_config.py      # Конфигурация storage
│   │   └── audit_log.py           # Аудит логи
│   │
│   ├── schemas/                   # Pydantic схемы (request/response)
│   │   ├── __init__.py
│   │   ├── file.py                # Схемы для файлов
│   │   ├── admin.py               # Схемы для admin endpoints
│   │   └── common.py              # Общие схемы
│   │
│   ├── services/                  # Бизнес-логика
│   │   ├── __init__.py
│   │   ├── file_service.py        # Операции с файлами
│   │   ├── storage_service.py     # Работа с хранилищем (local/S3)
│   │   ├── cache_service.py       # Управление кешем
│   │   ├── wal_service.py         # Write-Ahead Log
│   │   ├── reconcile_service.py   # Reconciliation между attr.json и DB
│   │   └── master_election.py     # Redis master election
│   │
│   ├── db/                        # База данных
│   │   ├── __init__.py
│   │   ├── session.py             # SQLAlchemy session
│   │   └── base.py                # Declarative base
│   │
│   └── utils/                     # Утилиты
│       ├── __init__.py
│       ├── file_utils.py          # Работа с файлами
│       ├── attr_utils.py          # Работа с *.attr.json
│       ├── redis_utils.py         # Redis helpers
│       └── metrics.py             # Prometheus metrics helpers
│
├── tests/                         # Тесты
│   ├── __init__.py
│   ├── conftest.py                # Pytest фикстуры
│   ├── unit/                      # Unit тесты
│   │   ├── test_file_service.py
│   │   ├── test_storage_service.py
│   │   └── test_wal_service.py
│   └── integration/               # Integration тесты
│       ├── test_file_api.py
│       ├── test_admin_api.py
│       └── test_health.py
│
├── alembic/                       # Database migrations
│   ├── versions/                  # Migration files
│   │   └── 001_initial.py
│   ├── env.py                     # Alembic environment
│   └── alembic.ini                # Alembic config
│
├── config/                        # Конфигурационные файлы
│   ├── config.yaml                # Основная конфигурация
│   └── config.yaml.example        # Пример конфигурации
│
├── logs/                          # Логи приложения (gitignored)
│   └── storage-element.log
│
├── .data/                         # Локальное хранилище файлов (gitignored)
│   └── storage/
│       └── 2025/01/09/12/         # /year/month/day/hour/
│           ├── file1.pdf
│           ├── file1.pdf.attr.json
│           ├── file2.docx
│           └── file2.docx.attr.json
│
├── Dockerfile                     # Docker образ
├── requirements.txt               # Python зависимости
├── README.md                      # Документация модуля
└── .env.example                   # Пример environment variables
```

## Ключевые файлы проекта

### Конфигурация

- **docker-compose.yml**: Базовая инфраструктура (PostgreSQL, Redis, MinIO, LDAP, Dex)
- **config/config.yaml**: Конфигурация модулей приложения
- **.env**: Environment variables (не в git)

### Документация

- **CLAUDE.md**: Инструкции для Claude Code
- **README.md**: Общая документация системы
- **DEVELOPMENT_PLAN.md**: План разработки по фазам
- **ARCHITECTURE_DECISIONS.md**: Архитектурные решения

### Модуль приложения

- **app/main.py**: FastAPI приложение, точка входа
- **app/core/config.py**: Конфигурация через Pydantic Settings
- **app/api/v1/router.py**: Главный router для всех endpoints
- **alembic/**: Database migrations

## Naming patterns для файлов

### Python модули
- `snake_case.py` для всех Python файлов
- `test_*.py` для файлов тестов

### Конфигурация
- `config.yaml` - основная конфигурация
- `.env` - environment variables

### Хранилище файлов
- `{name}_{username}_{timestamp}_{uuid}.{ext}` - файл
- `{name}_{username}_{timestamp}_{uuid}.{ext}.attr.json` - атрибуты

## Git ignored директории

- `.data/` - локальное хранилище файлов
- `logs/` - логи приложения
- `__pycache__/` - Python кеш
- `*.pyc` - скомпилированные Python файлы
- `.venv/` или `venv/` - виртуальные окружения
- `.env` - environment variables с секретами
- `htmlcov/` - coverage отчеты
- `.pytest_cache/` - pytest кеш

## Важные концепты организации

### Separation of Concerns
- **api/**: Только HTTP endpoints и валидация запросов
- **services/**: Вся бизнес-логика
- **models/**: Только ORM модели
- **schemas/**: Только Pydantic схемы для валидации

### Dependency Injection
- **api/deps.py**: Все зависимости FastAPI (get_db, get_current_user, get_redis)

### Configuration Management
- **core/config.py**: Центральная конфигурация через Pydantic Settings
- Environment variables переопределяют config.yaml

### Testing Structure
- **tests/unit/**: Тестируют отдельные функции и классы
- **tests/integration/**: Тестируют API endpoints и интеграции
- **tests/conftest.py**: Переиспользуемые фикстуры

## Directory hierarchy для storage

```
.data/storage/
└── {year}/              # 2025
    └── {month}/         # 01
        └── {day}/       # 09
            └── {hour}/  # 12
                ├── report_ivanov_20250109T120530_a1b2c3d4.pdf
                ├── report_ivanov_20250109T120530_a1b2c3d4.pdf.attr.json
                ├── doc_petrov_20250109T121045_e5f6g7h8.docx
                └── doc_petrov_20250109T121045_e5f6g7h8.docx.attr.json
```

Это обеспечивает:
- Удобное резервное копирование по периодам
- Простую навигацию по файлам
- Эффективное удаление старых данных
