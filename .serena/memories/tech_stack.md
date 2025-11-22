# ArtStore - Technology Stack

## Backend
- **Python 3.12+** с async/await, uvloop
- **FastAPI** для REST API
- **Uvicorn** ASGI server
- **Pydantic** для валидации
- **aiohttp** для HTTP клиента

## Database & Caching
- **PostgreSQL 15+** (asyncpg) - метаданные, full-text search
- **Redis 7** (sync redis-py) - Service Discovery, caching
- **Alembic** - database migrations

## Storage
- **Local Filesystem** или **S3/MinIO**
- **Write-Ahead Log** для атомарности

## Security
- **JWT RS256** токены
- **OAuth 2.0 Client Credentials**
- **TLS 1.3** transit encryption
- **Bcrypt** password hashing

## Monitoring
- **OpenTelemetry** distributed tracing
- **Prometheus** metrics collection
- **Grafana** visualization
- **JSON logging** для ELK/Splunk

## Frontend
- **Angular 17+** для Admin UI
- **TypeScript**
- **Angular Material**

## Infrastructure
- **Docker** multi-stage builds
- **Docker Compose** orchestration
- **Nginx** для Admin UI serving

## Development
- **pytest** для тестирования
- **black, isort, mypy, flake8** для quality
- **Git** с conventional commits
