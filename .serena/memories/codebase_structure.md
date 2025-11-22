# ArtStore - Codebase Structure

## Root Structure

```
artStore/
├── admin-module/              # Admin Module (8000)
├── storage-element/           # Storage Element (8010)
├── ingester-module/           # Ingester Module (8020)
├── query-module/              # Query Module (8030)
├── admin-ui/                  # Angular Admin UI (4200)
├── monitoring/                # Prometheus, Grafana configs
├── .venv/                     # ЕДИНЫЙ Python virtual environment
├── docker-compose.yml         # Главный compose файл
├── docker-compose.monitoring.yml  # Мониторинг стек
├── README-PROJECT.md          # Описание для новой команды
├── DEVELOPMENT-GUIDE.md       # Руководство по разработке
├── README.md                  # Детальная документация
└── CLAUDE.md                  # AI assistant instructions
```

## Python Module Structure (example: admin-module)

```
admin-module/
├── app/
│   ├── main.py                # FastAPI entry point
│   ├── core/                  # Configuration, security
│   ├── api/v1/endpoints/      # REST API endpoints
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic schemas
│   ├── services/              # Business logic
│   ├── db/                    # Database session
│   └── utils/                 # Utilities
├── tests/
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
├── alembic/                   # Database migrations
├── Dockerfile                 # Multi-stage production image
├── requirements.txt           # Python dependencies
├── pytest.ini                 # Pytest configuration
├── .env.example               # Environment variables example
└── README-PROJECT.md          # Module documentation
```

## Key Files

**Configuration**:
- `docker-compose.yml` - Infrastructure + Backend services
- `.env` - Environment variables (не в git)

**Documentation**:
- `README-PROJECT.md` - Project overview для новой команды
- `DEVELOPMENT-GUIDE.md` - Development methodology
- `<module>/README-PROJECT.md` - Module-specific docs

**Application**:
- `app/main.py` - FastAPI application entry point
- `app/core/config.py` - Pydantic Settings
- `alembic/` - Database migrations

## File Naming

**Python**: `snake_case.py`
**Tests**: `test_*.py`
**Config**: `config.yaml`, `.env`
**Storage**: `{name}_{username}_{timestamp}_{uuid}.{ext}`
**Attributes**: `{storage_filename}.attr.json`

## Directory Structure (Storage)

```
.data/storage/
└── {year}/
    └── {month}/
        └── {day}/
            └── {hour}/
                ├── file.pdf
                └── file.pdf.attr.json
```

## Git Ignored

- `.venv/` - Virtual environment
- `.data/` - Local file storage
- `logs/` - Application logs
- `__pycache__/`, `*.pyc`
- `.env` - Secrets
- `htmlcov/`, `.pytest_cache/`

## Docker Volumes

**ВАЖНО**: Logs и data в именованных volumes, НЕ в source directories!

```yaml
volumes:
  - admin_logs:/app/logs        # ✅ Правильно
  - storage_data:/app/.data     # ✅ Правильно
  # НЕ: ./admin-module:/app     # ❌ Неправильно!
```
