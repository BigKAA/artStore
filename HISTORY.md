# История развития проекта ArtStore

## О проекте

ArtStore - распределенная система файлового хранилища с микросервисной архитектурой, предназначенная для долгосрочного хранения документов с различными сроками хранения. Система построена на принципах отказоустойчивости, горизонтального масштабирования и разделения оперативного и архивного хранения.

## Ключевые принципы проекта

### Attribute-First Storage Model
**Point of Truth**: Файлы атрибутов (`*.attr.json`) являются единственным источником истины для метаданных файлов. Это критически важно для обеспечения backup'а элементов хранения как набора простых файлов без необходимости работы с отдельными таблицами БД.

### Distributed Storage Elements
Элементы хранения могут располагаться в разных ЦОД и иметь свои собственные кеш-БД для повышения производительности.

## Хронология развития архитектуры

### Этап 1: Базовая архитектура (v0.1)

**Основные компоненты:**
- Admin Module - центр управления и аутентификации
- Storage Element - физическое хранение файлов
- Ingester Module - добавление файлов
- Query Module - поиск и получение файлов
- Admin UI - графический интерфейс

**Технологические решения:**
- Python 3.12+ с FastAPI для backend
- Angular v20 с Bootstrap 5 для frontend
- PostgreSQL для хранения метаданных
- Redis для кеширования
- MinIO для S3-совместимого хранения

**Режимы работы storage-element:**
- `edit` - полный CRUD
- `rw` - чтение и запись, удаление запрещено
- `ro` - только чтение
- `ar` - архивный режим, только метаданные

### Этап 2: Аутентификация и авторизация (v0.2)

**JWT-based Authentication (RS256):**
- Асимметричное шифрование для безопасной распределенной валидации
- Admin Module генерирует токены приватным ключом
- Остальные модули валидируют локально публичным ключом
- Устранение необходимости сетевых запросов для каждой валидации

**Интеграция с внешними провайдерами:**
- Local authentication
- LDAP integration
- OAuth2 providers
- Гибридные режимы (local+LDAP, local+OAuth2)

### Этап 3: Service Discovery и координация (v0.3)

**Redis-based Service Discovery:**
- Admin Module публикует конфигурацию storage-element
- Ingester/Query модули подписываются на обновления
- Автоматическая синхронизация состояния системы
- Fallback на локальную конфигурацию при недоступности

**Stateless Design:**
- Все модули без сохранения состояния
- Горизонтальное масштабирование всех компонентов
- Shared storage для storage-element кластеров

### Этап 4: Высокая доступность и отказоустойчивость (v0.4)

**Устранение Single Points of Failure:**

1. **Load Balancer Cluster:**
   - HAProxy/Nginx в кластерной конфигурации
   - Keepalived для виртуального IP
   - Health checks и автоматическое исключение узлов

2. **Admin Module Cluster:**
   - Raft Consensus Protocol для leader election
   - Multi-Master Active-Active с 3+ узлами
   - Graceful Failover с RTO < 15 секунд
   - Split-Brain Protection через кворумные решения

3. **Redis Sentinel Cluster:**
   - 3+ Sentinel узла для High Availability
   - Automatic Failover с RTO < 30 секунд
   - Multi-Redis configuration для мониторинга

4. **Storage Element Clusters:**
   - Master Election через Redis Sentinel для режимов edit/rw
   - Shared Storage (NFS/S3) для всех узлов
   - Автоматический failover при недоступности мастера

**Circuit Breaker Pattern:**
- Graceful degradation при недоступности dependencies
- Экспоненциальный backoff для retry логики
- Health monitoring всех сервисов

### Этап 5: Консистентность данных (v0.5)

**Distributed Transactions:**

1. **Saga Pattern:**
   - Координация долгосрочных операций (загрузка → валидация → индексация)
   - Compensating actions для отката при сбоях
   - Admin Module Cluster как Saga Orchestrator

2. **Two-Phase Commit (2PC):**
   - Для критических операций изменения метаданных
   - Смена режимов storage-element
   - Перенос файлов между storage-element

3. **Write-Ahead Log (WAL):**
   - Журнал транзакций для атомарности операций
   - Гарантия записи файлов и атрибутов
   - Rollback при сбоях

**Conflict Resolution:**

1. **Vector Clocks:**
   - Глобальное упорядочивание событий
   - Синхронизация логического времени между компонентами
   - Admin Module Cluster управляет Vector Clock

2. **CRDT (Conflict-free Replicated Data Types):**
   - Для метаданных, изменяемых независимо
   - Автоматическое разрешение конфликтов

3. **Automatic Reconciliation:**
   - Обнаружение расхождений между storage-element
   - Автоматическое восстановление консистентности

**Протокол консистентности:**
```
WAL → Attr File → Vector Clock → DB Cache → Commit
```

### Этап 6: Оптимизация производительности (v0.6)

**Multi-Level Caching Strategy:**
- CDN (CloudFlare/AWS CloudFront) для популярных файлов
- Redis Cluster с partitioning для метаданных
- Local Cache (in-memory) на каждом узле
- PostgreSQL Query Cache с intelligent invalidation
- Cache Warming для предварительной загрузки

**PostgreSQL Full-Text Search:**
- Встроенные GIN индексы вместо ElasticSearch
- Триграммы (pg_trgm) для нечеткого поиска
- Real-time auto-complete
- Faceted search с оптимизированными индексами
- Search Results Caching в Redis (TTL: 10 минут)

**Streaming & Compression:**
- Chunked uploads/downloads для файлов >10MB
- Brotli/GZIP compression on-the-fly
- Resumable uploads/downloads
- Progress tracking

**Connection Pooling:**
- HTTP/2 persistent connections между всеми сервисами
- Минимизация latency
- Efficient resource utilization

**Async Processing:**
- Apache Kafka для heavy operations
- Background tasks для индексации и сжатия
- Parallel processing множественных файлов

### Этап 7: Комплексная система безопасности (v0.7)

**TLS 1.3 Transit Encryption:**
- Все межсервисные соединения защищены TLS 1.3
- Certificate pinning для защиты от MITM
- Perfect Forward Secrecy с эфемерными ключами
- End-to-end encryption от клиента до storage

**Automated JWT Key Rotation:**
- Ротация RS256 ключевых пар каждые 24 часа
- Key Versioning для плавного перехода
- 48-часовой Grace Period для старых токенов
- Автоматическое распространение через Redis Sentinel

**Fine-grained RBAC:**
- Resource-level permissions
- Детализированный контроль доступа к файлам
- Storage-element specific permissions
- Role-based access control

**Comprehensive Audit Logging:**
- Tamper-proof логирование всех операций
- Цифровые подписи записей аудита
- Structured logging в JSON формате
- Complete access trail для compliance

**API Security:**
- API Rate Limiting с adaptive защитой
- DDoS Protection на уровне HTTP proxy
- Request Signing для критических операций
- CORS configuration с explicit whitelisting

**Real-time Security Monitoring:**
- Автоматическое обнаружение suspicious activities
- Pattern detection для аномалий
- Automated incident response
- Security alerts и notifications

### Этап 8: Advanced Monitoring и Observability (v0.8)

**OpenTelemetry Distributed Tracing:**
- Trace Correlation с уникальными trace ID
- Span Instrumentation для всех операций
- Context Propagation через headers и message queues
- Performance Profiling критических операций

**Custom Business Metrics по модулям:**

1. **Admin Module:**
   - Authentication performance (JWT validation time)
   - User management metrics
   - Storage element health monitoring
   - Cluster coordination metrics (Raft, leader elections)

2. **Storage Element:**
   - File upload latency по размерам файлов
   - Storage utilization и прогнозы заполнения
   - Cache hit ratios (PostgreSQL metadata cache)
   - Mode transition metrics (edit → rw → ro → ar)

3. **Ingester Module:**
   - File upload performance по storage-element
   - Transfer success rates
   - Queue processing metrics (Kafka)
   - Compression efficiency

4. **Query Module:**
   - Search performance по сложности запросов
   - Search quality metrics (relevance, user interaction)
   - Download performance по размерам
   - Cache efficiency (Local → Redis → PostgreSQL)

**Third-party Analytics Integration:**
- Prometheus metrics export для Grafana, DataDog, New Relic
- Structured logging для ELK Stack, Splunk
- OpenTelemetry traces для APM platforms (Jaeger, Zipkin)
- Custom dashboards через API

## Технологический стек

### Backend
- **Python 3.12+** с uvloop для максимальной производительности
- **FastAPI** с async/await для конкурентной обработки
- **SQLAlchemy** (async mode) с connection pooling
- **PostgreSQL 15+** с query optimization
- **aiofiles** для асинхронных файловых операций

### Поиск и индексирование
- **PostgreSQL Full-Text Search** с GIN индексами
- **pg_trgm** для триграммного поиска
- **Apache Kafka** для асинхронной обработки
- **Background Tasks** для индексации

### Кеширование и координация
- **Redis Sentinel Cluster** для High Availability
- **Local Cache** (in-memory) для hot data
- **CDN Integration** (CloudFlare/AWS CloudFront)

### Производительность
- **HTTP/2** persistent connections
- **Brotli/GZIP** compression
- **Connection pooling** для всех внешних сервисов
- **Async I/O** для файловых операций

### Инфраструктура
- **HAProxy/Nginx** load balancer cluster
- **Docker** с multi-stage builds
- **Prometheus/Grafana** для мониторинга

### Безопасность
- **TLS 1.3** для всех соединений
- **RS256 JWT** с автоматической ротацией
- **Digital signatures** для audit logs
- **Certificate pinning** для MITM защиты

### Мониторинг
- **OpenTelemetry** для distributed tracing
- **Prometheus** для метрик
- **Structured Logging** (JSON) для анализа

### Frontend
- **Angular v20** с TypeScript
- **Bootstrap 5** для UI
- **RxJS** для reactive programming

## Архитектурные паттерны

### Distributed Systems
- **Saga Pattern** - долгосрочные транзакции
- **Two-Phase Commit** - критические операции
- **Circuit Breaker** - защита от каскадных сбоев
- **Retry with Exponential Backoff** - устойчивость к временным сбоям

### Consistency
- **Vector Clocks** - упорядочивание событий
- **CRDT** - conflict-free репликация
- **Write-Ahead Log** - атомарность операций
- **Automatic Reconciliation** - восстановление консистентности

### High Availability
- **Raft Consensus** - leader election
- **Multi-Master Active-Active** - распределение нагрузки
- **Sentinel Pattern** - автоматический failover
- **Graceful Degradation** - работа при частичных сбоях

### Performance
- **Multi-Level Caching** - иерархия кешей
- **Connection Pooling** - эффективное использование соединений
- **Streaming** - обработка больших файлов
- **Async Processing** - background обработка

### Security
- **Zero Trust Architecture** - проверка каждого запроса
- **Defense in Depth** - многоуровневая защита
- **Audit Trail** - полное логирование
- **Automated Key Rotation** - регулярная смена ключей

## Эволюция требований

### Исходные требования
1. Разделение физического хранилища на части
2. Быстрое восстановление после сбоев
3. Отказоустойчивость приложений
4. Однозначность данных и атрибутов (attribute-first model)
5. Горячее и холодное хранение
6. Режим только для чтения
7. Предельный срок хранения
8. Версионность документов

### Дополненные требования
1. **Устранение всех SPOF** - полная отказоустойчивость системы
2. **Строгая консистентность данных** - Saga, 2PC, Vector Clocks
3. **Высокая производительность** - multi-level caching, PostgreSQL FTS
4. **Комплексная безопасность** - TLS 1.3, JWT rotation, RBAC, audit
5. **Advanced Monitoring** - OpenTelemetry, custom metrics, analytics
6. **Горизонтальное масштабирование** - stateless design, clustering

## Ключевые решения и их обоснование

### 1. PostgreSQL Full-Text Search вместо ElasticSearch
**Решение:** Использовать встроенные возможности PostgreSQL
**Обоснование:**
- Упрощение архитектуры (меньше компонентов)
- Достаточная производительность для наших нагрузок
- GIN индексы обеспечивают быстрый поиск
- Консистентность данных (одна БД вместо двух систем)
- Снижение операционных расходов

### 2. Attribute-First Storage Model
**Решение:** Файлы `*.attr.json` как source of truth
**Обоснование:**
- Простота backup (набор обычных файлов)
- Восстановление без БД (атрибуты рядом с файлами)
- Надежность (файловая система более устойчива)
- Независимость от БД для критических данных

### 3. Redis Sentinel вместо простого Redis
**Решение:** Кластер Redis Sentinel для HA
**Обоснование:**
- Устранение SPOF в Service Discovery
- Автоматический failover < 30 секунд
- Кворумные решения предотвращают split-brain
- Graceful degradation с fallback на локальную конфигурацию

### 4. Raft Consensus для Admin Module
**Решение:** Кластер с Raft протоколом
**Обоснование:**
- Distributed leader election
- Гарантии консистентности
- Автоматическое переключение лидера
- Защита от split-brain

### 5. Saga Pattern для файловых операций
**Решение:** Координация через Saga Orchestrator
**Обоснование:**
- Долгосрочные операции (загрузка → валидация → индексация)
- Compensating actions для отката
- Устойчивость к сбоям
- Прозрачность процесса

### 6. Vector Clocks для упорядочивания событий
**Решение:** Глобальные векторные часы
**Обоснование:**
- Распределенная система без центральных часов
- Упорядочивание конкурентных операций
- Обнаружение конфликтов
- Консистентность без строгой синхронизации

### 7. TLS 1.3 для всех соединений
**Решение:** Обязательное шифрование transit encryption
**Обоснование:**
- Защита данных при передаче
- Perfect Forward Secrecy
- Современный безопасный протокол
- Compliance с требованиями безопасности

### 8. Автоматическая ротация JWT ключей
**Решение:** Смена ключей каждые 24 часа
**Обоснование:**
- Минимизация окна компрометации
- Соответствие best practices
- Плавный переход (grace period)
- Автоматизация без ручного вмешательства

## Milestone проекта

### M1: Базовая функциональность
- ✅ Создание базовой структуры модулей
- ✅ Реализация CRUD операций для пользователей
- ✅ Реализация storage-element с режимами работы
- ✅ Basic authentication и authorization

### M2: Service Discovery и координация
- ✅ Интеграция Redis для Service Discovery
- ✅ Реализация stateless design
- ✅ Горизонтальное масштабирование модулей
- ✅ Health checks и liveness/readiness probes

### M3: Высокая доступность (в процессе)
- ✅ Redis Sentinel Cluster
- ✅ Admin Module Cluster с Raft
- ✅ Load Balancer Cluster
- ✅ Circuit Breaker Pattern
- ⏳ Storage Element Cluster с master election

### M4: Консистентность данных (в процессе)
- ✅ Saga Pattern design
- ✅ Vector Clock architecture
- ⏳ Saga Orchestrator implementation
- ⏳ Two-Phase Commit для критических операций
- ⏳ Automatic Reconciliation

### M5: Оптимизация производительности (в процессе)
- ✅ PostgreSQL Full-Text Search
- ✅ Multi-Level Caching architecture
- ⏳ CDN Integration
- ⏳ Streaming uploads/downloads
- ⏳ Background processing через Kafka

### M6: Комплексная безопасность (в процессе)
- ✅ TLS 1.3 architecture
- ✅ JWT RS256 implementation
- ⏳ Automated key rotation
- ⏳ Fine-grained RBAC
- ⏳ Comprehensive audit logging

### M7: Advanced Monitoring (в процессе)
- ✅ Prometheus metrics
- ⏳ OpenTelemetry integration
- ⏳ Custom business metrics
- ⏳ Third-party analytics integration

### M8: Admin UI (в процессе)
- ✅ Базовая структура Angular приложения
- ⏳ User management interface
- ⏳ Storage element monitoring
- ⏳ File manager

### M9: Production Ready (запланировано)
- ⏳ Full test coverage
- ⏳ Performance testing
- ⏳ Security audit
- ⏳ Documentation completion
- ⏳ Deployment automation

### M10: Advanced Features (запланировано)
- ⏳ ЭЦП module integration
- ⏳ Advanced file versioning
- ⏳ Retention policy automation
- ⏳ Compliance reporting

## Будущие направления развития

### Краткосрочные (3-6 месяцев)
1. Завершение кластерной архитектуры для всех компонентов
2. Полная реализация Saga Pattern и Vector Clocks
3. Интеграция CDN для популярных файлов
4. Automated key rotation для JWT
5. OpenTelemetry distributed tracing

### Среднесрочные (6-12 месяцев)
1. Machine Learning для предиктивного cache warming
2. Automated capacity planning
3. Advanced analytics и reporting
4. Multi-region support
5. Disaster recovery automation

### Долгосрочные (12+ месяцев)
1. Edge computing integration
2. AI-powered search и recommendations
3. Blockchain для immutable audit trail
4. Quantum-resistant cryptography
5. Zero-knowledge encryption

## Уроки и выводы

### Что сработало хорошо
1. **Attribute-first model** - упростил backup и восстановление
2. **Microservices architecture** - позволил масштабировать независимо
3. **Stateless design** - сделал масштабирование тривиальным
4. **PostgreSQL FTS** - достаточно для наших нагрузок
5. **Circuit Breaker** - защитил от каскадных сбоев

### Что можно улучшить
1. **Complexity** - архитектура стала довольно сложной
2. **Testing** - нужно больше integration и e2e тестов
3. **Documentation** - требуется постоянное обновление
4. **Monitoring** - еще не полностью реализован observability
5. **Security** - некоторые features еще в разработке

### Ключевые принципы на будущее
1. **Simplicity first** - добавлять сложность только когда необходимо
2. **Measure everything** - метрики для всех решений
3. **Security by design** - безопасность с самого начала
4. **Test early** - тестирование на всех этапах
5. **Document continuously** - документация как код

---

**Последнее обновление:** 2025-09-30
**Версия документа:** 1.0
**Статус проекта:** Active Development