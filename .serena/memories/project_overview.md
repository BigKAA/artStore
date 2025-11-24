# Обзор проекта ArtStore

## Назначение проекта

**ArtStore** — распределенная система файлового хранилища с микросервисной архитектурой для долгосрочного хранения документов с различными сроками хранения.

### Цели системы
- Распределенное хранение с возможностью размещения в разных ЦОД
- Автоматическое управление жизненным циклом документов
- Горячее и холодное хранение для оптимизации затрат
- Отказоустойчивость без единых точек отказа (SPOF)
- Гибкая система доступа с детализированным контролем прав

## Архитектура системы

### Микросервисы

1. **Admin Module** (порты 8000-8009)
   - OAuth 2.0 аутентификация (Client Credentials flow)
   - Управление Service Accounts и правами
   - Координация распределенных транзакций (Saga Pattern)
   - Service Discovery через Redis
   - Высокая доступность через Raft consensus

2. **Storage Element** (порты 8010-8019)
   - Физическое хранение файлов (Local FS/S3/MinIO)
   - Кеш метаданных в PostgreSQL
   - Write-Ahead Log для атомарности
   - Режимы: edit, rw, ro, ar
   - Attribute-first model: `*.attr.json` как источник истины

3. **Ingester Module** (порты 8020-8029)
   - Прием и валидация файлов
   - Streaming upload с chunked передачей
   - Автоматическое сжатие (Brotli/GZIP)
   - Распределение файлов между Storage Elements

4. **Query Module** (порты 8030-8039)
   - Поиск файлов по метаданным (PostgreSQL Full-Text Search)
   - Multi-level caching (Local → Redis → PostgreSQL)
   - Resumable downloads
   - Load balancing между Storage Elements

5. **Admin UI** (порт 4200)
   - Angular-based административный интерфейс
   - Управление пользователями и Service Accounts
   - Мониторинг Storage Elements
   - Файловый менеджер с поиском

### Инфраструктурные компоненты
- **PostgreSQL 15+**: Основная СУБД для метаданных
- **Redis 7**: Service Discovery, distributed caching
- **MinIO / S3**: Опциональное объектное хранилище
- **Prometheus + Grafana**: Мониторинг и метрики
- **OpenTelemetry**: Distributed tracing

## Технологический стек

### Backend
- Python 3.12+ с async/await
- FastAPI для REST API
- SQLAlchemy (async mode) + Asyncpg
- Alembic для миграций
- Redis-py (синхронный режим) для Service Discovery
- Pydantic для валидации

### Frontend
- Angular для Admin UI

### Infrastructure
- Docker с multi-stage builds
- Docker Compose для оркестрации
- HAProxy/Nginx для load balancing
- Keepalived для HA балансировщиков

### Security
- JWT RS256 для аутентификации
- OAuth 2.0 Client Credentials
- TLS 1.3 для межсервисных соединений
- Automated Key Rotation

### Monitoring
- OpenTelemetry для tracing
- Prometheus для метрик
- Grafana для визуализации
- Structured JSON logging

## Ключевые принципы

1. **Attribute-First Storage Model**: Файлы `*.attr.json` - единственный источник истины
2. **Consistency Protocol**: WAL → Attr File → DB Cache → Service Discovery
3. **Stateless Design**: Все сервисы stateless для горизонтального масштабирования
4. **Circuit Breaker**: Graceful degradation при недоступности зависимостей
5. **Redis SYNC Mode**: Синхронный redis-py для Service Discovery
6. **PostgreSQL ASYNC**: Asyncpg для database операций