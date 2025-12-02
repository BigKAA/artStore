# ArtStore - Распределенное файловое хранилище

## Обзор проекта

**ArtStore** — это распределенная система файлового хранилища с микросервисной архитектурой, предназначенная для долгосрочного хранения документов с различными сроками хранения. Система реализует принципы отказоустойчивости, горизонтального масштабирования и обеспечивает разделение оперативного и архивного хранения.

## Цель проекта

Создание высоконадежной, масштабируемой системы хранения файлов с поддержкой:
- **Распределенного хранения** с возможностью размещения в разных ЦОД
- **Автоматического управления жизненным циклом** документов с различными сроками хранения
- **Горячего и холодного хранения** для оптимизации затрат
- **Отказоустойчивости** без единых точек отказа (SPOF)
- **Гибкой системы доступа** с детализированным контролем прав

## Архитектура системы

### Микросервисная архитектура

Система построена на базе микросервисов, каждый из которых выполняет строго определенные функции:

#### Управляющий контур

1. **Load Balancer Cluster** (HAProxy/Nginx + keepalived)
   - Распределение входящего трафика между всеми модулями
   - Устранение единой точки отказа через keepalived
   - Health checks и автоматическое исключение недоступных узлов

2. **Admin Module Cluster** (порты 8000-8009)
   - Центр управления всей системой
   - OAuth 2.0 аутентификация (Client Credentials flow)
   - Генерация JWT токенов с RS256 подписью
   - Управление Service Accounts и правами доступа
   - Координация распределенных транзакций (Saga Pattern)
   - Публикация конфигурации Storage Elements в Service Discovery
   - Raft consensus протокол для leader election (3+ узла)
   - Автоматический failover (RTO < 15 секунд)

3. **Ingester Module Cluster** (порты 8020-8029)
   - Прием и валидация загружаемых файлов
   - Streaming upload с chunked передачей
   - Автоматическое сжатие (Brotli/GZIP)
   - Распределение файлов между Storage Elements
   - Участие в распределенных транзакциях
   - Circuit Breaker для graceful degradation

4. **Query Module Cluster** (порты 8030-8039)
   - Поиск файлов по метаданным (PostgreSQL Full-Text Search)
   - Multi-level caching (Local → Redis → PostgreSQL)
   - Оптимизированная выдача файлов с resumable downloads
   - Real-time search с auto-complete
   - Load balancing между Storage Elements

5. **Admin UI** (порт 4200)
   - Angular-based административный интерфейс
   - Управление пользователями и Service Accounts
   - Мониторинг Storage Elements
   - Файловый менеджер с поиском
   - Dashboard с системной статистикой

#### Хранилище данных

**Storage Element Clusters** (порты 8010-8019)
- Физическое хранение файлов (Local FS или S3/MinIO)
- Кеш метаданных в PostgreSQL для производительности
- Write-Ahead Log для атомарности операций
- Четыре режима работы: `edit`, `rw`, `ro`, `ar`
- Attribute-first model: `*.attr.json` как источник истины
- Master election через Redis Sentinel (для режимов edit/rw)

### Инфраструктурные компоненты

- **PostgreSQL 15+**: Основная СУБД для метаданных, full-text search
- **Redis 7** (Cluster mode): Service Discovery, distributed caching, master election
- **MinIO / S3**: Опциональное объектное хранилище для файлов
- **Prometheus + Grafana**: Мониторинг и метрики
- **OpenTelemetry**: Distributed tracing для всех микросервисов

## Ключевые технологии

### Backend
- **Python 3.12+** с async/await и uvloop
- **FastAPI** для REST API с автодокументацией
- **SQLAlchemy** (async mode) для работы с PostgreSQL
- **Asyncpg** для высокопроизводительного доступа к БД
- **Alembic** для миграций схемы БД
- **Redis.asyncio** (асинхронный режим) для Service Discovery и кеширования
- **Pydantic** для валидации данных и конфигурации

### Frontend
- **Angular** для Admin UI

### Infrastructure
- **Docker** с multi-stage builds для всех модулей
- **Docker Compose** для оркестрации сервисов
- **HAProxy/Nginx** для load balancing
- **Keepalived** для HA балансировщиков

### Security
- **JWT RS256** для аутентификации между сервисами
- **OAuth 2.0 Client Credentials** для API клиентов
- **Automated Key Rotation** (JWT каждые 24 часа, secrets каждые 90 дней)
- **PostgreSQL SSL** для шифрования database соединений (опционально, для production)

#### Типы учетных записей

ArtStore использует **два типа учетных записей**:

1. **System Administrators** (AdminUser) - для людей, управляющих системой через Admin UI
   - Аутентификация: Login/Password
   - Роли: SUPER_ADMIN, ADMIN, READONLY
   - API: `/api/admin-auth/*` и `/api/admin-users/*`

2. **Service Accounts** - для machine-to-machine API доступа внешних систем
   - Аутентификация: OAuth 2.0 Client Credentials
   - Роли: ADMIN, USER, AUDITOR, READONLY
   - API: `/api/auth/token` и `/api/service-accounts/*`

Детальное описание см. [Admin Module README](admin-module/README.md#15-типы-учетных-записей)

**Механизмы аутентификации** подробно описаны в документе [AUTH-MECHANICS.md](admin-module/AUTH-MECHANICS.md)

### Monitoring & Observability
- **OpenTelemetry** для distributed tracing
- **Prometheus** для сбора метрик
- **Grafana** для визуализации и dashboards
- **Structured JSON logging** для интеграции с ELK/Splunk

## Принципы разработки

### Отказоустойчивость и High Availability

1. **Устранение Single Points of Failure (SPOF)**
   - Все компоненты развернуты в кластерной конфигурации
   - Automatic failover с минимальным RTO (< 15-30 секунд)
   - Split-brain protection через кворумные решения

2. **Circuit Breaker Pattern**
   - Автоматическое отключение недоступных зависимостей
   - Graceful degradation с использованием кешей
   - Экспоненциальный backoff при retry

3. **Stateless Design**
   - Все сервисы stateless для горизонтального масштабирования
   - Сессионное состояние в Redis Cluster
   - Отсутствие локальных данных критичных для работы

### Консистентность данных

1. **Attribute-First Storage Model**
   - Файлы атрибутов (`*.attr.json`) как единственный источник истины
   - Максимальный размер 4KB для гарантии атомарности записи
   - Write-Ahead Log → Temporary file → fsync → Atomic Rename

2. **Распределенные транзакции**
   - **Saga Pattern** для долгосрочных операций (upload, delete, transfer)
   - **Two-Phase Commit** для критических операций смены режимов
   - **Automatic Reconciliation** при обнаружении несоответствий

3. **Гарантии порядка операций**
   - Attr.json записывается первым
   - Database cache обновляется после attr.json
   - Service Discovery уведомляется последним
   - Rollback процедуры при сбоях на любом этапе

### Производительность

1. **Multi-Level Caching**
   - CDN layer (опционально)
   - Redis Cluster для метаданных и результатов поиска
   - Local in-memory cache на каждом узле
   - PostgreSQL query cache

2. **PostgreSQL Full-Text Search**
   - GIN индексы для мгновенного поиска
   - Без необходимости в ElasticSearch для базового функционала
   - Оптимизированные query планы

3. **Streaming и Compression**
   - Chunked upload/download для больших файлов
   - On-the-fly compression (Brotli/GZIP)
   - HTTP/2 persistent connections
   - Resumable transfers

### Безопасность

1. **Multi-Layer Security**
   - JWT RS256 с automated key rotation
   - OAuth 2.0 для machine-to-machine auth
   - Fine-grained RBAC на уровне ресурсов

2. **Audit & Compliance**
   - Comprehensive audit logging с tamper-proof storage
   - Real-time monitoring suspicious activities
   - Automated compliance reporting (GDPR, SOX, HIPAA)
   - 7+ лет retention для audit logs

3. **Database Security (PostgreSQL SSL)**
   - SSL-шифрование для database соединений (опционально)
   - Поддержка режимов: `disable`, `require`, `verify-ca`, `verify-full`
   - Certificate-based authentication для максимальной безопасности
   - По умолчанию SSL выключен (backward compatible)

## Storage Element Selection Strategy

### Sequential Fill Algorithm

При загрузке файлов Ingester Module автоматически выбирает оптимальный Storage Element используя алгоритм Sequential Fill:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Sequential Fill Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ SE #1    │     │ SE #2    │     │ SE #3    │               │
│   │ P:1      │ ──► │ P:2      │ ──► │ P:3      │               │
│   │ ████████ │     │ ██████░░ │     │ ██░░░░░░ │               │
│   │ 95% FULL │     │ 75% OK   │     │ 25% OK   │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│        │                │                                        │
│        ▼                │                                        │
│   SKIP (FULL)          SELECT                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Логика выбора:**
1. Storage Elements сортируются по `priority` (ascending)
2. Для каждого SE в порядке priority проверяется:
   - `capacity_status != FULL`
   - `can_accept_file(file_size)` - достаточно свободного места
3. Возвращается первый подходящий SE

**Retention Policy → Storage Mode:**
| Retention Policy | Target Mode | Description |
|-----------------|-------------|-------------|
| `TEMPORARY` | `edit` | Файлы с ограниченным TTL, автоудаление по истечении |
| `PERMANENT` | `rw` | Файлы для долгосрочного архивного хранения |

### Adaptive Capacity Thresholds

Система использует адаптивные пороги ёмкости вместо фиксированных, что позволяет эффективнее использовать хранилище разного размера:

```
┌─────────────────────────────────────────────────────────────────┐
│               Adaptive Thresholds Formula                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   warning_free = max(total_gb × 15%, 150GB)                     │
│   critical_free = max(total_gb × 8%, 80GB)                      │
│   full_free = max(total_gb × 2%, 20GB)                          │
│                                                                  │
│   threshold% = (total - free_limit) / total × 100               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Примеры для RW Storage:**
| SE Size | Warning | Critical | Full | Waste |
|---------|---------|----------|------|-------|
| 1TB | 85% | 92% | 98% | 2% |
| 10TB | 98.5% | 99.2% | 99.8% | 0.2% |
| 100TB | 98.5% | 99.2% | 99.8% | 0.2% |

**Capacity Status Levels:**
- `OK` - Нормальная работа, приём файлов разрешён
- `WARNING` - Предупреждение админам, приём продолжается
- `CRITICAL` - Срочное предупреждение, приём продолжается
- `FULL` - SE исключается из выбора, перенаправление на следующий SE

### Fallback Pattern

При недоступности основного источника информации о SE система автоматически переключается на резервные:

```
Redis Registry → Admin Module API → Local Config
     │                  │                │
     │ Sorted Sets      │ HTTP Fallback  │ Environment
     │ Real-time        │ API            │ Variables
     │ health data      │ Cached data    │ Static config
     ▼                  ▼                ▼
   Primary           Secondary        Emergency
```

## File Lifecycle Management

### Two-Phase Commit Finalization

Процесс финализации временных файлов в постоянное хранение реализован через Two-Phase Commit:

```
┌─────────────────────────────────────────────────────────────────┐
│              Two-Phase Commit: Finalization                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Phase 1: PREPARE                                              │
│   ┌─────────┐                    ┌─────────┐                    │
│   │ Edit SE │ ────copy────────► │  RW SE  │                    │
│   │ (temp)  │                    │ (perm)  │                    │
│   └─────────┘                    └─────────┘                    │
│       │                              │                          │
│       │        Verify copy OK        │                          │
│       │◄─────────────────────────────┤                          │
│       │                                                          │
│   Phase 2: COMMIT                                               │
│       │        Update metadata       │                          │
│       ├─────────────────────────────►│                          │
│       │                              │                          │
│       │        Schedule cleanup      │                          │
│       ├─────────────────────────────►│ (24h safety margin)      │
│       │                                                          │
│   COMPLETED                                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Этапы финализации:**
1. **PREPARE**: Копирование файла с Edit SE на RW SE
2. **VERIFY**: Проверка целостности копии (checksum validation)
3. **COMMIT**: Обновление метаданных, смена `retention_policy` на PERMANENT
4. **SCHEDULE_CLEANUP**: Добавление source файла в очередь удаления (+24h)

### Garbage Collection

Автоматическая очистка файлов выполняется фоновым GC Job каждые 6 часов:

```
┌─────────────────────────────────────────────────────────────────┐
│                  Garbage Collection Strategies                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   1. TTL-Based Cleanup                                          │
│      ┌─────────────────────────────────────────────┐            │
│      │ TEMPORARY files where ttl_expires_at <= now │            │
│      │ → Add to cleanup queue (NORMAL priority)    │            │
│      └─────────────────────────────────────────────┘            │
│                                                                  │
│   2. Finalized Files Cleanup                                    │
│      ┌─────────────────────────────────────────────┐            │
│      │ Files finalized > 24 hours ago              │            │
│      │ → Delete from source (Edit) SE              │            │
│      └─────────────────────────────────────────────┘            │
│                                                                  │
│   3. Orphaned Files Cleanup                                     │
│      ┌─────────────────────────────────────────────┐            │
│      │ Files on SE without DB records (age > 7d)   │            │
│      │ → Add to cleanup queue (LOW priority)       │            │
│      └─────────────────────────────────────────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Safety Features:**
- 24-hour safety margin после финализации перед удалением
- 7-day grace period для orphaned файлов
- Retry logic (max 3 attempts) для transient failures
- Batch processing для ограничения нагрузки

**Cleanup Queue Priorities:**
| Priority | Value | Use Case |
|----------|-------|----------|
| `HIGH` | 3 | Manual deletion requests |
| `NORMAL` | 2 | TTL expiration, finalized files |
| `LOW` | 1 | Orphaned files cleanup |

### Health Reporting

Storage Elements периодически публикуют статус в Redis Registry:

```
┌─────────────────────────────────────────────────────────────────┐
│                  Health Reporting Flow                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Storage Element                     Redis Registry            │
│   ┌─────────────┐                    ┌─────────────┐            │
│   │ SE #1       │ ──────────────────►│ Hash        │            │
│   │             │   Every 30 sec     │ storage:    │            │
│   │ Capacity:   │   (configurable)   │ elements:   │            │
│   │  - total    │                    │ {se_id}     │            │
│   │  - used     │                    │             │            │
│   │  - free     │                    │ TTL: 90s    │            │
│   │  - status   │                    └─────────────┘            │
│   │             │                                                │
│   │ Health:     │                    ┌─────────────┐            │
│   │  - healthy  │ ──────────────────►│ Sorted Set  │            │
│   │             │   ZADD/ZREM        │ storage:    │            │
│   └─────────────┘                    │ {mode}:     │            │
│                                      │ by_priority │            │
│                                      └─────────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Redis Keys:**
- `storage:elements:{se_id}` - Hash с полными метаданными SE
- `storage:{mode}:by_priority` - Sorted Set для Sequential Fill (score = priority)

**При FULL статусе:** SE автоматически удаляется из sorted sets и не выбирается для новых файлов

#### PostgreSQL SSL Configuration

**Basic Setup (Production)**:
```bash
# Включить SSL для всех модулей
DB_SSL_ENABLED=true
DB_SSL_MODE=require  # Обязательное SSL соединение
```

**Advanced Setup (Maximum Security)**:
```bash
# Полная проверка сертификата
DB_SSL_ENABLED=true
DB_SSL_MODE=verify-full
DB_SSL_CA_CERT=/app/ssl-certs/ca-cert.pem
DB_SSL_CLIENT_CERT=/app/ssl-certs/client-cert.pem  # опционально
DB_SSL_CLIENT_KEY=/app/ssl-certs/client-key.pem    # опционально
```

**SSL Modes**:
- `disable` - Без SSL (development, по умолчанию)
- `require` - SSL обязателен, без проверки сертификата (рекомендуется для production)
- `verify-ca` - SSL + проверка CA сертификата
- `verify-full` - SSL + проверка CA + hostname (максимальная безопасность)

**Модули с поддержкой SSL**:
- Admin Module
- Storage Element
- Query Module
- *(Ingester Module не использует database напрямую)*

Детальная информация: см. модульные README.md для примеров конфигурации.

## Режимы работы Storage Elements

### EDIT (Редактирование)
- **Полный CRUD**: создание, чтение, изменение, удаление файлов
- **Использование**: оперативное хранилище для документов в работе
- **Ограничения**: настраиваемый срок хранения, автоматическая очистка устаревших
- **Переход**: невозможен через API (фиксированный режим)

### RW (Чтение-Запись)
- **Операции**: создание и чтение файлов, запрет удаления
- **Использование**: архивное хранилище с определенным сроком
- **Заполнение**: после заполнения переходит в режим RO
- **Переход**: RW → RO (через API)

### RO (Только чтение)
- **Операции**: только чтение файлов
- **Использование**: долгосрочное архивное хранение
- **Защита**: невозможность изменения или удаления
- **Переход**: RO → AR (через API)

### AR (Архив)
- **Хранение**: только метаданные локально (`*.attr.json`)
- **Файлы**: на съемных носителях (магнитные ленты, offline storage)
- **Восстановление**: через Restore Storage Element с webhook уведомлениями
- **TTL**: 30 дней для восстановленных файлов

## Структура проекта

```
artStore/
├── admin-module/              # Admin Module Cluster
├── storage-element/           # Storage Element
├── ingester-module/           # Ingester Cluster
├── query-module/              # Query Cluster
├── admin-ui/                  # Angular Admin UI
├── monitoring/                # Prometheus, Grafana, AlertManager
├── docker-compose.yml         # Базовая инфраструктура
├── docker-compose.monitoring.yml  # Мониторинг стек
├── CLAUDE.md                  # Инструкции для AI-ассистента
└── README-PROJECT.md          # Основная документация (Этот файл)
```

Подробное описание каждого модуля смотрите в соответствующих `README.md` файлах в директориях модулей.

## Методология разработки

### Git Workflow
- **Feature branches** для всех изменений
- **Main branch** защищена, только через Pull Requests
- **Conventional Commits** для автоматической генерации CHANGELOG
- **Semantic Versioning** для релизов

### Testing Strategy
- **Unit tests** (pytest) для бизнес-логики
- **Integration tests** для API endpoints и межмодульного взаимодействия
- **E2E tests** (опционально) для критических пользовательских сценариев
- **Coverage target**: минимум 80% для production кода

### CI/CD (планируется)
- Автоматический запуск тестов на каждый commit
- Линтеры и форматтеры (black, isort, mypy, flake8)
- Security scanning (bandit, safety)
- Automated Docker image builds
- Deployment в Kubernetes (production)

## Development Environment

### Требования
- **Docker** и **Docker Compose**
- **Python 3.12+** с venv
- **Node.js 18+** для Admin UI (Angular)
- **Git**

### Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone <repository-url>
cd artStore

# 2. Создать виртуальное окружение Python (ЕДИНЫЙ для всех модулей)
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или: .venv\Scripts\activate  # Windows

# 3. Установить зависимости для всех Python модулей
pip install -r admin-module/requirements.txt
pip install -r storage-element/requirements.txt
pip install -r ingester-module/requirements.txt
pip install -r query-module/requirements.txt

# 4. Запустить базовую инфраструктуру
docker-compose up -d

# 5. Запустить мониторинг (опционально)
docker-compose -f docker-compose.monitoring.yml up -d

# 6. Проверить доступность сервисов
# PostgreSQL: localhost:5432
# Redis: localhost:6379
# MinIO: localhost:9000 (console: 9001)
# Prometheus: localhost:9090
# Grafana: localhost:3000 (admin/admin123)
```

### Тестирование

```bash
# Тесты конкретного модуля (из корня проекта)
source .venv/bin/activate
pytest admin-module/tests/ -v
pytest storage-element/tests/ -v --cov=app

# Docker-based тестирование (рекомендуется)
docker-compose build storage-element
docker-compose run --rm storage-element pytest tests/ -v
```

## Мониторинг и метрики

### Prometheus Metrics
Все модули экспортируют метрики на `/metrics` endpoint:
- HTTP request latency и throughput
- Database query performance
- Redis operations timing
- Custom business metrics (file operations, search performance)

### Grafana Dashboards
- **ArtStore - System Overview**: общий обзор системы
- **Module-specific dashboards**: детальные метрики по модулям
- **Storage utilization**: использование дискового пространства
- **Performance analytics**: анализ производительности

### Alerts (AlertManager)
- **Critical**: Service down, high error rate (>5%), high latency (>500ms p95)
- **Warning**: High CPU/Memory (>80%), connection pool exhaustion, low disk space

## Roadmap

### Completed (Sprints 1-23)
- ✅ Базовая инфраструктура (PostgreSQL, Redis, MinIO)
- ✅ Admin Module с OAuth 2.0 authentication
- ✅ Storage Element с WAL и режимами работы
- ✅ Ingester Module с streaming uploads
- ✅ Query Module с full-text search
- ✅ Comprehensive monitoring stack (Prometheus, Grafana)
- ✅ JWT RS256 authentication с automated rotation

### In Progress (Sprint 24+)
- 🔄 Admin UI development (Angular)
- 🔄 Raft consensus для Admin Module Cluster
- 🔄 Redis Cluster для HA Service Discovery
- 🔄 Webhook system для событий (file_restored, restore_failed, file_expiring)

### Planned (Future Sprints)
- 📋 Kafka integration для async processing
- 📋 CDN integration (CloudFlare/AWS CloudFront)
- 📋 Advanced search (filters, facets, relevance tuning)
- 📋 Backup & restore automation
- 📋 Kubernetes deployment manifests
- 📋 CI/CD pipeline (GitHub Actions / GitLab CI)

## Контакты и поддержка

Для вопросов и предложений по разработке обращайтесь к технической документации в директории проекта:
- [CLAUDE.md](CLAUDE.md) - инструкции для AI-ассистента
- [README.md](README.md) - детальная техническая документация
- Модуль-специфичные README-PROJECT.md в директориях каждого модуля

## Лицензия

Проприетарное программное обеспечение. Все права защищены.
