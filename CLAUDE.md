# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ArtStore - это распределенная система файлового хранилища с микросервисной архитектурой, предназначенная для долгосрочного хранения документов с различными сроками хранения. Система реализует принципы отказоустойчивости, горизонтального масштабирования и обеспечивает разделение оперативного и архивного хранения.

### Core Architecture Concepts

**Attribute-First Storage Model**: Система использует файлы атрибутов (`*.attr.json`) как единственный источник истины для метаданных файлов. Это критически важно для обеспечения backup'а элементов хранения как набора простых файлов без необходимости работы с отдельными таблицами БД.

**Distributed Storage Elements**: Элементы хранения могут располагаться в разных ЦОД и иметь свои собственные кеш-БД для повышения производительности.

**JWT-based Authentication (RS256)**: Центральная аутентификация через Admin Module с распределенной валидацией токенов через публичный ключ.

**Service Discovery**: Координация через Redis Cluster - Admin Module Cluster публикует конфигурацию storage-element, а Ingester/Query кластеры подписываются на эти обновления с fallback на локальную конфигурацию.

**High Availability Architecture**: Полное устранение Single Points of Failure:
- **Load Balancer Cluster**: HAProxy/Nginx с keepalived для распределения трафика
- **Admin Module Cluster**: Raft consensus с 3+ узлами и automatic leader election (RTO < 15 сек)
- **Redis Cluster**: 6+ узлов (минимум 3 master + 3 replica) с automatic failover и горизонтальным масштабированием (RTO < 30 сек)
- **Storage Element Clusters**: Кластеризация с shared storage и master election
- **Circuit Breaker Patterns**: Graceful degradation при недоступности dependencies

**Data Consistency Framework**: Система обеспечивает строгую консистентность данных через:
- **Saga Pattern**: Для долгосрочных операций с файлами (загрузка → валидация → индексация)
- **Two-Phase Commit**: Для критических операций изменения метаданных и смены режимов
- **Vector Clocks**: Глобальное упорядочивание событий между распределенными компонентами
- **Write-Ahead Log**: Атомарность операций записи файлов и атрибутов
- **CRDT**: Conflict-free Replicated Data Types для метаданных, изменяемых независимо
- **Automatic Reconciliation**: Автоматическое восстановление консистентности при расхождениях

**Performance Optimization Framework**: Комплексная стратегия повышения производительности:
- **Multi-Level Caching**: CDN → Redis Cluster → Local Cache → Database Cache
- **PostgreSQL Full-Text Search**: Встроенные возможности поиска с GIN индексами для метаданных
- **Streaming & Compression**: Chunked uploads/downloads с Brotli/GZIP compression
- **Connection Pooling**: HTTP/2 persistent connections между всеми сервисами
- **Async Processing**: Background tasks через Kafka для heavy operations

**Comprehensive Security Framework**: Многоуровневая система защиты данных:
- **TLS 1.3 Transit Encryption**: Все межсервисные соединения защищены современным протоколом TLS 1.3
- **Secure Key Management**: Защищенное управление JWT ключами через Admin Module Cluster
- **Automated JWT Key Rotation**: Ротация RS256 ключей каждые 24 часа с плавным переходом
- **Fine-grained RBAC**: Детализированная ролевая модель с resource-level permissions
- **Comprehensive Audit Logging**: Tamper-proof логирование с цифровыми подписями
- **API Rate Limiting**: Adaptive защита от DDoS атак и злоупотреблений
- **Real-time Security Monitoring**: Автоматическое обнаружение и блокировка угроз

**Advanced Monitoring и Observability Framework**: Комплексная система наблюдаемости:
- **OpenTelemetry Distributed Tracing**: Полное отслеживание запросов через все микросервисы
- **Custom Business Metrics**: File upload latency, search performance, storage utilization, authentication metrics
- **Third-party Analytics Integration**: Экспорт метрик для внешних систем аналитики

## Development Environment Setup

### Prerequisites
```bash
# Ensure base infrastructure is running
docker-compose up -d
```

### Database Access
```bash
# Access PostgreSQL container for database operations
docker exec -it artstore_postgres psql -U artstore -d artstore

# Create additional databases as needed within the container
```

### Service Ports
- **PostgreSQL**: 5432
- **PgAdmin**: 5050 (admin@admin.com / password)
- **Redis**: 6379
- **MinIO**: 9000 (console: 9001, minioadmin / minioadmin)
- **Admin Module**: 8000-8009
- **Storage Elements**: 8010-8019
- **Ingester Module**: 8020-20
- **Query Module**: 8030
- **Admin UI**: 4200

## Module Architecture

### 1. Admin Module Cluster (admin-module/)
**Role**: Отказоустойчивый центр аутентификации и управления системой
- **Raft Consensus Cluster**: Автоматическое лидерство с выборами в кластере 3+ узлов
- **Multi-Master Active-Active**: Consistent hashing для распределения нагрузки
- **Zero-Downtime Operations**: Rolling updates и graceful failover (RTO < 15 сек)
- JWT token generation (RS256) с распределенной валидацией
- **Saga Orchestrator**: Координация распределенных транзакций
- **Vector Clock Manager**: Управление глобальным упорядочиванием событий
- **Conflict Resolution Engine**: Разрешение конфликтов данных между storage-element
- User and storage element management
- Service Discovery publishing to Redis Cluster
- Prometheus metrics endpoint

**Key APIs**:
- `/api/auth/*` - Authentication endpoints
- `/api/users/*` - User management
- `/api/storage-elements/*` - Storage element management
- `/api/transactions/*` - Saga orchestration and Vector Clock management
- `/health/*` - Health checks
- `/metrics` - Prometheus metrics

### 2. Storage Element Clusters (storage-element/)
**Role**: Отказоустойчивое физическое хранение файлов с кешированием метаданных
- **Clustered Architecture**: Множественные узлы за Load Balancer Cluster
- **Master Election via Redis Cluster**: Distributed leader election для режимов edit/rw
- **Automatic Failover**: Переключение мастера за < 30 секунд с split-brain protection
- **Shared Storage Access**: NFS/S3 кластерный доступ для всех узлов
- File storage (local filesystem or S3)
- **Write-Ahead Log**: Журнал транзакций для атомарности операций
- **Vector Clock Integration**: Локальные векторные часы для упорядочивания
- **Saga Participant**: Участие в распределенных транзакциях
- Metadata caching in PostgreSQL Cluster
- Four operational modes: edit, rw, ro, ar

**Critical Features**:
- Attribute files (*.attr.json) as source of truth
- **Consistency Protocol**: WAL → Attr File → Vector Clock → DB Cache → Commit
- **Automatic Reconciliation**: Обнаружение и устранение несоответствий
- Directory structure: `/year/month/day/hour/`
- Master coordination through Redis for write modes
- Mode transitions: edit (fixed) → rw → ro → ar

### 3. Ingester Cluster (ingester-module/)
**Role**: Высокопроизводительное отказоустойчивое добавление и управление файлами
- **Streaming Upload**: Chunked загрузка с progress tracking и resumable uploads
- **Parallel Processing**: Одновременная обработка множественных файлов
- **Compression On-the-fly**: Автоматическое сжатие (Brotli/GZIP) при загрузке
- **CDN Pre-upload**: Автоматическая репликация на CDN для популярных файлов
- **Kafka Integration**: Асинхронная обработка через message queue
- **Circuit Breaker Integration**: Graceful degradation при недоступности storage-element
- **Redis Cluster Client**: Подключение к HA Redis Cluster для Service Discovery
- **Local Config Fallback**: Кеширование конфигурации при недоступности Service Discovery
- **Saga Transactions**: Координируемые операции загрузки файлов
- **Compensating Actions**: Автоматический откат при сбоях
- File upload to storage elements with optimization
- File deletion (edit mode only) with async cleanup
- File transfer between storage elements with Two-Phase Commit

### 4. Query Cluster (query-module/)
**Role**: Высокопроизводительный отказоустойчивый поиск и получение файлов
- **PostgreSQL Full-Text Search**: Мгновенный поиск через встроенные GIN индексы PostgreSQL
- **Multi-Level Caching**: Local → Redis → PostgreSQL Query Cache
- **Real-time Search**: Auto-complete и suggestions на основе популярных запросов
- **CDN Integration**: Автоматическое направление на ближайший CDN endpoint
- **Connection Pooling**: HTTP/2 persistent connections к storage-element
- **Load Balanced Cluster**: Множественные узлы за Load Balancer для высокой доступности
- **Circuit Breaker Pattern**: Автоматическое отключение недоступных storage-element
- **Redis Cluster Integration**: HA подключение к Service Discovery
- **Consistent Queries**: Поиск с учетом Vector Clock для консистентности
- **Conflict Detection**: Обнаружение конфликтов между storage-element
- **Read Consistency**: Гарантии согласованности при чтении
- File search by metadata with full-text capabilities
- Optimized file download with resumable transfers
- Digital signature verification

### 5. Admin UI (admin-ui/)
**Role**: Angular-based administrative interface
- User management interface
- Storage element monitoring
- File manager
- System statistics dashboard

## Development Commands

### Running Applications
```bash
# Start base infrastructure
docker-compose up -d

# Run specific module in development (example for admin-module)
cd admin-module
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Build and run with Docker (preferred method)
docker-compose -f docker-compose-app.yml up --build -d
```

### Testing
Always create and run unit tests for modified code:
```bash
# Run tests for specific module
cd [module-name]
py -m pytest tests/ -v

# Run with coverage
py -m pytest tests/ --cov=app --cov-report=html
```

### Database Operations
```bash
# Create new database within container
docker exec -it artstore_postgres createdb -U artstore new_database_name

# Access database
docker exec -it artstore_postgres psql -U artstore -d [database_name]
```

## Key Configuration Patterns

### Authentication Configuration
```yaml
auth:
  jwt:
    public_key_path: "/path/to/public_key.pem"
    algorithm: "RS256"
```

### Storage Configuration
```yaml
storage:
  type: "local"  # or "s3"
  max_size: 1Gb
  local:
    base_path: "./.data/storage"
  s3:
    endpoint_url: "http://localhost:9000"
    bucket_name: "artstore-files"
```

### Database Configuration
```yaml
database:
  host: "localhost"
  port: 5432
  username: "artstore"
  password: "password"
  database: "artstore"
  table_prefix: "storage_elem_01"  # For uniqueness in shared DB
```

## Storage Element Modes and Transitions

**Mode Definitions**:
- `edit`: Full CRUD operations (default for active storage)
- `rw`: Read-write, no deletion (transitional state)
- `ro`: Read-only (archived but accessible)
- `ar`: Archive mode (metadata only, files on cold storage)

**Transition Rules**:
- edit → Cannot be changed via API
- rw → ro (via API)
- ro → ar (via API)
- ar → other modes (configuration change + restart only)

## Development Workflow

1. **Module Development Order**: admin-module → storage-element → ingester-module → query-module → admin-ui
2. **Container Usage**: Each module gets its own Docker container; admin-ui uses nginx
3. **Configuration Priority**: Environment variables override config file settings
4. **Language**: All comments and documentation should be in Russian
5. **Platform**: Development on Windows 11 using cmd.exe or PowerShell commands

## Testing Credentials

**Default Admin User**:
- Username: `admin`
- Password: `admin123`
- Change in production!

**Infrastructure Credentials**:
- PostgreSQL: artstore / password
- PgAdmin: admin@admin.com / password
- MinIO: minioadmin / minioadmin

## Critical Implementation Notes

### High Availability Requirements
1. **No Single Points of Failure**: Все компоненты развернуты в кластерной конфигурации
2. **Load Balancer Cluster**: HAProxy/Nginx + keepalived для устранения SPOF входного трафика
3. **Admin Module Cluster**: Raft consensus кластер 3+ узлов с automatic leader election (RTO < 15 сек)
4. **Redis Cluster**: 6+ узлов (минимум 3 master + 3 replica) с automatic failover и горизонтальным масштабированием (RTO < 30 сек)
5. **Circuit Breaker Pattern**: Обязательная реализация для всех inter-service communications
6. **Local Fallback**: Кеширование конфигурации для работы при недоступности Service Discovery

### Data Consistency & Operations
7. **Consistency Protocol**: WAL → Attr File → Vector Clock → DB Cache → Commit (строго в этом порядке)
8. **Saga Coordination**: Admin Module Cluster координирует все долгосрочные операции через Saga Pattern
9. **Vector Clock Sync**: Все модули синхронизируют логическое время через Admin Module Cluster
10. **Conflict Resolution**: Автоматическое обнаружение и разрешение конфликтов данных
11. **Attribute Files**: Always write to *.attr.json first, then update database cache
12. **Master Election**: Required for edit/rw modes using Redis Cluster coordination
13. **Service Discovery**: Ingester/Query clusters must subscribe to Redis Cluster for storage element updates
14. **Stateless Design**: All modules must be stateless
15. **Error Handling**: Insufficient storage space should return specific error message
16. **Retention Management**: Storage elements have configurable retention periods with automatic warnings

### Performance Requirements
17. **PostgreSQL Full-Text Search**: Встроенные GIN индексы для поиска по метаданным всех storage-element
18. **Multi-Level Caching**: CDN → Redis → Local → DB cache hierarchy реализация
19. **Connection Pooling**: HTTP/2 persistent connections между всеми сервисами
20. **Streaming Operations**: Chunked upload/download для файлов >10MB
21. **Background Processing**: Kafka message queue для heavy operations (compression, indexing)
22. **CDN Integration**: Автоматическая репликация файлов на CloudFlare/AWS CloudFront

## Monitoring and Logging

### Advanced Monitoring Requirements

All modules must implement comprehensive observability:

#### OpenTelemetry Integration (Mandatory)
- **Distributed Tracing**: Полное инструментирование всех HTTP requests, database queries, Redis operations
- **Trace Correlation**: Уникальные trace ID для корреляции across all микросервисы
- **Span Context Propagation**: Передача trace context через headers и message queues
- **Performance Profiling**: Детальное профилирование критических операций

#### Custom Business Metrics (Required)
- **File Operation Metrics**: Upload/download latency, success rates, error types
- **Search Performance**: Query response time, result relevance, cache efficiency
- **Storage Utilization**: Disk usage, growth rates, capacity forecasting
- **Authentication Metrics**: JWT validation time, key rotation frequency, security events
- **System Health**: Memory usage, CPU utilization, garbage collection metrics


#### Third-party Analytics Integration
- **Metrics Export**: Prometheus metrics для integration с external analytics platforms (Grafana, DataDog, New Relic)
- **Log Aggregation**: Structured logs для ELK Stack, Splunk, и других log analysis систем
- **Trace Data**: OpenTelemetry traces для external APM platforms (Jaeger, Zipkin)
- **Custom Dashboards**: API для integration с external monitoring и business intelligence систем

#### Standard Monitoring (Baseline)
- Prometheus metrics at `/metrics`
- Health checks at `/health/live` and `/health/ready`
- Structured logging (JSON format mandatory)
- Connection pool monitoring for database connections
- Real-time dashboard integration (Grafana/custom dashboards)

## Security Considerations

### Comprehensive Security Requirements

#### Encryption Standards
- **File Storage**: Файлы хранятся в незашифрованном виде для обеспечения совместимости и простоты backup процедур
- **TLS 1.3 transit encryption**: Все межсервисные соединения должны использовать TLS 1.3
- **Secure Key Management**: JWT ключи защищены и управляются через Admin Module Cluster
- **JWT Key Rotation**: Автоматическая ротация JWT ключей каждые 24 часа
- **Perfect Forward Secrecy**: Эфемерные ключи для каждой TLS сессии

#### Identity & Access Management
- **JWT tokens expire**: 30 minutes (access) / 7 days (refresh) с automatic refresh
- **Fine-grained RBAC**: Resource-level permissions обязательны для файловых операций
- **Temporary Access Tokens**: Поддержка time-limited tokens для external integrations
- **Multi-factor Authentication**: Обязательна для административных аккаунтов
- **Password Policy**: Минимум 12 символов, bcrypt hashing, rotation каждые 90 дней

#### API Security
- **Bearer token authentication**: Обязательна для всех API endpoints кроме health checks
- **API Rate Limiting**: Adaptive limiting с автоматической блокировкой при превышении
- **Request Signing**: Цифровая подпись критических операций (upload, delete, transfer)
- **IP Whitelisting**: Configurable ограничения по IP для административных операций
- **CORS Configuration**: Строгая политика Same-Origin с explicit domain whitelisting

#### Audit & Compliance
- **Comprehensive Audit Logging**: Все операции логируются с tamper-proof signatures
- **Real-time Monitoring**: Автоматическое обнаружение и alerting suspicious activities
- **Data Retention**: Audit logs хранятся minimum 7 лет с encrypted backup
- **Compliance Reporting**: Automated генерация GDPR, SOX, HIPAA compliance reports
- **Incident Response**: Automated isolation и notification при security breaches

#### Production Security Standards
- **System admin protection**: Cannot be deleted or demoted, требует dual approval
- **Secrets Management**: Все credentials в защищенной конфигурации с encryption at rest
- **Certificate Management**: Automated renewal и validation SSL/TLS certificates
- **Vulnerability Scanning**: Weekly automated scans с mandatory patching SLA
- **Penetration Testing**: Quarterly external security assessments обязательны