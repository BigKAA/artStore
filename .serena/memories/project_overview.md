# ArtStore - Project Overview

## Назначение

ArtStore - распределенная система файлового хранилища с микросервисной архитектурой для долгосрочного хранения документов с различными сроками хранения.

## Статус проекта

Проект находится в активной разработке с полной инфраструктурой и базовыми модулями.

## Документация

**Главная документация**:
- `README-PROJECT.md` - Полное описание проекта для новой команды
- `DEVELOPMENT-GUIDE.md` - Руководство по разработке и тестированию
- `README.md` - Детальная техническая документация
- `CLAUDE.md` - Инструкции для AI-ассистента

**Модульная документация**:
- `admin-module/README-PROJECT.md` - OAuth 2.0, Saga orchestration
- `storage-element/README-PROJECT.md` - Attribute-first storage, WAL
- `ingester-module/README-PROJECT.md` - Streaming uploads, Circuit Breaker
- `query-module/README-PROJECT.md` - Full-text search, Caching
- `admin-ui/README-PROJECT.md` - Angular UI

## Ключевые архитектурные концепции

**Attribute-First Storage**: `*.attr.json` как единственный источник истины для метаданных

**JWT Authentication (RS256)**: Центральная аутентификация через Admin Module

**Service Discovery**: Redis Pub/Sub для координации Storage Elements

**High Availability**: Полное устранение SPOF через кластеризацию всех компонентов

**Data Consistency**: Saga Pattern + Two-Phase Commit + WAL

**Performance**: Multi-level caching, PostgreSQL Full-Text Search, Streaming

**Security**: TLS 1.3, Automated key rotation, Fine-grained RBAC

**Monitoring**: OpenTelemetry tracing, Prometheus metrics, Grafana dashboards

## Docker Infrastructure

**КРИТИЧЕСКИ ВАЖНО**: Использовать ТОЛЬКО `docker-compose.yml` из корня проекта!

**Запуск**:
```bash
cd /home/artur/Projects/artStore
docker-compose up -d  # Вся система
docker-compose -f docker-compose.monitoring.yml up -d  # Мониторинг
```

**Services**:
- Infrastructure: PostgreSQL, Redis, MinIO, PgAdmin
- Backend: admin-module (8000), storage-element (8010), ingester-module (8020), query-module (8030)
- Monitoring: Prometheus (9090), Grafana (3000), AlertManager (9093)

## Python Virtual Environment

**ЕДИНЫЙ venv для всех модулей**: `/home/artur/Projects/artStore/.venv`

```bash
source /home/artur/Projects/artStore/.venv/bin/activate
pip install -r admin-module/requirements.txt
pip install -r storage-element/requirements.txt
pip install -r ingester-module/requirements.txt
pip install -r query-module/requirements.txt
```

## Testing

**Unit tests**: `pytest <module>/tests/unit/ -v`
**Integration tests**: `pytest <module>/tests/integration/ -v`
**Docker-based**: `docker-compose run --rm <module> pytest tests/ -v`

## Credentials

**PostgreSQL**: artstore / password
**Redis**: localhost:6379 (no auth)
**MinIO**: minioadmin / minioadmin
**PgAdmin**: admin@admin.com / password
**Grafana**: admin / admin123
