# ArtStore - Обзор проекта

## Назначение

ArtStore - это распределенная система файлового хранилища с микросервисной архитектурой, предназначенная для долгосрочного хранения документов с различными сроками хранения. Система реализует принципы отказоустойчивости, горизонтального масштабирования и обеспечивает разделение оперативного и архивного хранения.

## Статус проекта

Проект находится на начальной стадии разработки:
- ✅ Базовая инфраструктура развернута через docker-compose.yml
- 🔄 Модули приложений в процессе разработки

## Основные компоненты

### Управляющий контур
- **Load Balancer Cluster**: HAProxy/Nginx с keepalived
- **Admin Module Cluster**: Raft consensus с 3+ узлами (порты 8000-8009)
- **Admin UI**: Angular-интерфейс (порт 4200)
- **Ingester Cluster**: Загрузка и управление файлами (порты 8020-8029)
- **Query Cluster**: Поиск и получение файлов (порты 8030-8039)

### Элемент хранения
- **Storage Element Clusters**: Физическое хранение файлов (порты 8010-8019)
- **PostgreSQL**: Кеш метаданных
- **Local FS / S3**: Физическое хранилище файлов

## Базовая инфраструктура (Docker Compose)

- PostgreSQL 15 (localhost:5432, artstore/password)
- PgAdmin (localhost:5050, admin@admin.com/password)
- Redis 7 (localhost:6379)
- MinIO (localhost:9000/9001, minioadmin/minioadmin)
- LDAP 389ds (localhost:1389, cn=Directory Manager/password, dc=artstore,dc=local)
- Dex OIDC (localhost:5556/5557/5558)

## Ключевые архитектурные концепции

### Attribute-First Storage Model
Файлы атрибутов (`*.attr.json`) - единственный источник истины для метаданных файлов. Критично для backup элементов хранения как набора простых файлов.

### JWT-based Authentication (RS256)
Центральная аутентификация через Admin Module с распределенной валидацией токенов через публичный ключ.

### Service Discovery
Координация через Redis Cluster - Admin Module публикует конфигурацию storage-element, а Ingester/Query подписываются на обновления.

### High Availability
- Load Balancer Cluster с keepalived
- Admin Module Cluster с Raft consensus (RTO < 15 сек)
- Redis Cluster 6+ узлов (RTO < 30 сек)
- Storage Element Clusters с master election
- Circuit Breaker Patterns

### Data Consistency
- Saga Pattern для долгосрочных операций
- Two-Phase Commit для критических операций
- Write-Ahead Log для атомарности
- Automatic Reconciliation при расхождениях

### Performance Optimization
- Multi-Level Caching (CDN → Redis → Local → DB)
- PostgreSQL Full-Text Search с GIN индексами
- Streaming & Compression (Brotli/GZIP)
- Connection Pooling (HTTP/2)
- Async Processing через Kafka

### Security
- TLS 1.3 transit encryption
- Automated JWT Key Rotation (каждые 24 часа)
- LDAP/AD Integration с mapping групп на роли
- Fine-grained RBAC
- Comprehensive Audit Logging

### Monitoring & Observability
- OpenTelemetry Distributed Tracing
- Custom Business Metrics
- Third-party Analytics Integration
- Prometheus metrics endpoint
