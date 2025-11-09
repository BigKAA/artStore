# ArtStore - Технологический стек

## Языки программирования

### Backend
- **Python >=3.12** с uvloop для максимальной производительности
- FastAPI с async/await для конкурентной обработки
- SQLAlchemy (async mode) с connection pooling

### Frontend
- **Angular** для Admin UI

## База данных

- **PostgreSQL >=15** с query optimization
- Asyncpg для асинхронных операций
- Alembic для миграций
- GIN индексы для full-text search

## Кеширование и очереди

- **Redis 7** (через aioredis)
  - Service Discovery
  - Distributed Caching
  - Master Election через Redis Sentinel
- **Apache Kafka** для асинхронной обработки

## Хранилище файлов

- **Local Filesystem** или **S3** (MinIO)
- Структура директорий: `/year/month/day/hour/`

## Аутентификация и безопасность

- **JWT tokens (RS256)** для аутентификации
- **LDAP 389ds** (через ldap3) для корпоративной аутентификации
- **Dex OIDC** как провайдер OAuth2
- **TLS 1.3** для межсервисных соединений

## Поиск и индексирование

- **PostgreSQL Full-Text Search** с GIN индексами
- **ElasticSearch 8.x** (опционально) для продвинутого поиска
- **Apache Kafka** для асинхронной индексации
- **Apache Tika** для full-text поиска внутри документов

## Инфраструктура

- **Docker** с multi-stage builds
- **HAProxy/Nginx** load balancer cluster
- **Keepalived** для HA балансировщиков
- **Redis Sentinel** для HA Redis

## Мониторинг и наблюдаемость

- **OpenTelemetry** для distributed tracing
- **Prometheus** для метрик
- **Grafana** для визуализации
- Structured logging (JSON format)
- ELK Stack / Splunk интеграция

## Оптимизация производительности

- **uvloop** для event loop
- **Brotli/GZIP** compression
- **HTTP/2** persistent connections
- **CDN Integration** (CloudFlare/AWS CloudFront)
- Connection pooling для всех сервисов
- Async I/O для файловых операций

## Разработка и тестирование

- **pytest** для unit и integration тестов
- **Docker Compose** для локальной разработки
- **Alembic** для миграций БД
- **uvicorn** для запуска FastAPI приложений
