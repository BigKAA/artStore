# План разработки ArtStore (Application Focus)

## Executive Summary

**ArtStore** - распределенная система файлового хранилища с микросервисной архитектурой для долгосрочного хранения документов.

**Текущий статус**: ✅ Базовая инфраструктура развернута через docker-compose.yml и готова к разработке

**Сроки разработки приложения:**
- **MVP**: 2-3 месяца (базовая функциональность)
- **Production-Ready**: 4-6 месяцев (с HA компонентами)
- **Enterprise-Grade**: 7-9 месяцев (полный функционал)

**Доступная инфраструктура:**
- ✅ PostgreSQL 15 (localhost:5432, artstore/password)
- ✅ PgAdmin (localhost:5050, admin@admin.com/password)
- ✅ Redis 7 (localhost:6379)
- ✅ MinIO (localhost:9000/9001, minioadmin/minioadmin)
- ✅ LDAP 389ds (localhost:1389, cn=Directory Manager/password, dc=artstore,dc=local)
- ✅ Dex OIDC (localhost:5556/5557/5558)
- ✅ Nginx (localhost:80/443 с TLS)

---

## Архитектура приложения

```
┌─────────────────────────────────────────────────────────────┐
│              Nginx Reverse Proxy (✅ готов)                  │
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
    ┌────────▼─────────┐           ┌─────────▼────────┐
    │  Admin Module    │           │  Ingester Module │
    │  Port: 8000      │◄─────────►│  Port: 8020      │
    │  • JWT Auth      │           │  • Upload        │
    │  • LDAP (✅)     │           │  • Compression   │
    │  • User CRUD     │           │                  │
    └────────┬─────────┘           └─────────┬────────┘
             │                                │
             │         Redis (✅)              │
             │         Service Discovery      │
             │                                │
    ┌────────▼────────┐           ┌─────────▼────────┐
    │  Storage        │           │  Query Module    │
    │  Element        │◄─────────►│  Port: 8030      │
    │  Port: 8010     │           │  • Search (FTS)  │
    │  • *.attr.json  │           │  • Download      │
    │  • MinIO/Local  │           │  • Cache         │
    └────────┬────────┘           └──────────────────┘
             │
    ┌────────▼────────┐
    │  PostgreSQL (✅) │
    │  Metadata Cache │
    └─────────────────┘
```

---

## Фазы разработки приложения

### ФАЗА 0: ✅ Инфраструктура (ЗАВЕРШЕНО)

Базовая инфраструктура развернута и работает. **Переходим сразу к разработке приложения.**

---

### ФАЗА 1: Admin Module (Недели 1-3)

**Цель**: Центральный модуль аутентификации и управления

#### Неделя 1: Базовая структура и подключения

**Задачи**:
1. Создать структуру FastAPI проекта admin-module/
2. Настроить подключение к PostgreSQL (asyncpg)
3. Настроить подключение к Redis (aioredis)
4. Настроить подключение к LDAP (ldap3)
5. Создать базовые модели (User, StorageElement)
6. Настроить Alembic для миграций

**Deliverables**:
- ✅ admin-module/app/ структура
- ✅ Подключения к БД, Redis, LDAP работают
- ✅ Health endpoints: /health/live, /health/ready
- ✅ Базовая конфигурация через .env

**Команды для проверки**:
```bash
cd admin-module
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health/live
```

---

#### Неделя 2: Authentication System

**Задачи**:
1. Реализовать JWT token generation (HS256 для MVP)
2. Реализовать LDAP authentication
3. Создать endpoints: POST /api/auth/login, /api/auth/refresh
4. Реализовать password fallback (local DB если LDAP недоступен)
5. Создать FastAPI dependencies для auth
6. Написать unit tests для authentication

**Deliverables**:
- ✅ POST /api/auth/login (username/password → access_token + refresh_token)
- ✅ POST /api/auth/refresh (refresh_token → new access_token)
- ✅ LDAP integration working
- ✅ JWT middleware для защиты endpoints
- ✅ Tests: tests/test_auth.py

**Примеры запросов**:
```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# Response: {"access_token": "...", "refresh_token": "...", "expires_in": 1800}
```

---

#### Неделя 3: User Management & Storage Registry

**Задачи**:
1. Реализовать CRUD для users (только admin)
2. Реализовать RBAC (roles: admin, user, readonly)
3. Создать registry для storage elements в PostgreSQL
4. Реализовать Service Discovery publishing в Redis
5. Создать endpoints для storage element management
6. Написать интеграционные тесты

**Deliverables**:
- ✅ GET/POST/PUT/DELETE /api/users (admin only)
- ✅ GET/POST/PUT/DELETE /api/storage-elements (admin only)
- ✅ PostgreSQL schema для users и storage_elements
- ✅ Redis pub/sub для storage config updates
- ✅ RBAC enforcement на всех endpoints

**PostgreSQL Schema**:
```sql
-- admin-module database: artstore_admin
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255),
    password_hash VARCHAR(255),  -- для local auth fallback
    role VARCHAR(20) NOT NULL,  -- admin, user, readonly
    ldap_dn VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE storage_elements (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    mode VARCHAR(10) NOT NULL,  -- edit, rw, ro, ar
    storage_type VARCHAR(20) NOT NULL,  -- local, s3
    base_path TEXT,
    max_size_bytes BIGINT,
    current_size_bytes BIGINT DEFAULT 0,
    retention_days INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### ФАЗА 2: Storage Element (Недели 4-6)

**Цель**: Реализация физического хранения файлов с метаданными

#### Неделя 4: Core Storage Implementation

**Задачи**:
1. Создать структуру storage-element/ проекта
2. Реализовать Attribute-First Storage (*.attr.json)
3. Реализовать file naming convention
4. Реализовать directory structure (/YYYY/MM/DD/HH/)
5. Реализовать local и MinIO storage backends
6. Создать atomic write mechanism (WAL → temp → rename)

**Deliverables**:
- ✅ storage-element/app/ структура
- ✅ AttributeFile.write_atomic() working
- ✅ generate_storage_filename() с truncation
- ✅ DirectoryManager для /YYYY/MM/DD/HH/
- ✅ LocalStorage и MinIOStorage backends

**Attr.json Schema**:
```json
{
  "original_filename": "report.pdf",
  "storage_filename": "report_ivanov_20250109T120000_uuid.pdf",
  "username": "ivanov",
  "upload_timestamp": "2025-01-09T12:00:00Z",
  "file_size": 2457600,
  "content_type": "application/pdf",
  "uuid": "a1b2c3d4-...",
  "retention_days": 2555,
  "metadata": {"department": "Finance"},
  "checksum": {"algorithm": "SHA256", "value": "e3b0c..."}
}
```

---

#### Неделя 5: PostgreSQL Metadata Cache

**Задачи**:
1. Создать PostgreSQL schema для metadata cache
2. Реализовать sync_from_attr_file() для indexing
3. Реализовать reconcile_all() для consistency check
4. Создать GIN indexes для full-text search
5. Реализовать file search queries
6. Написать reconciliation tests

**Deliverables**:
- ✅ PostgreSQL table: storage_elem_01_files
- ✅ GIN index на (original_filename, metadata)
- ✅ Automatic reconciliation каждые 15 минут
- ✅ Search queries < 100ms
- ✅ Conflict resolution (attr.json wins)

**PostgreSQL Schema**:
```sql
-- storage-element database: artstore_storage
CREATE TABLE storage_elem_01_files (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL,
    storage_filename VARCHAR(255) UNIQUE NOT NULL,
    original_filename TEXT NOT NULL,
    username VARCHAR(100) NOT NULL,
    upload_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    file_size BIGINT NOT NULL,
    content_type VARCHAR(100),
    retention_days INTEGER,
    metadata JSONB,
    checksum_value VARCHAR(128),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_files_fts ON storage_elem_01_files
USING GIN (to_tsvector('russian', original_filename || ' ' || COALESCE(metadata::text, '')));

CREATE INDEX idx_files_uuid ON storage_elem_01_files (uuid);
CREATE INDEX idx_files_username ON storage_elem_01_files (username);
```

---

#### Неделя 6: Mode Management & API

**Задачи**:
1. Реализовать mode transitions (edit → rw → ro → ar)
2. Создать file CRUD endpoints
3. Реализовать JWT validation через Admin Module public key
4. Реализовать Service Discovery subscription
5. Создать health checks
6. Написать E2E tests для storage operations

**Deliverables**:
- ✅ GET /api/files/:uuid (retrieve file info)
- ✅ GET /api/files/:uuid/download (file download)
- ✅ DELETE /api/files/:uuid (edit mode only)
- ✅ GET /api/files/search?q=query (metadata search)
- ✅ Mode transition API
- ✅ JWT validation middleware

---

### ФАЗА 3: Ingester Module (Недели 7-9)

**Цель**: Высокопроизводительная загрузка файлов

#### Неделя 7: Streaming Upload

**Задачи**:
1. Создать структуру ingester-module/ проекта
2. Реализовать streaming upload (chunked 10MB)
3. Реализовать progress tracking в Redis
4. Реализовать resumable uploads
5. Реализовать compression on-the-fly (Brotli)
6. Интеграция с Storage Element API

**Deliverables**:
- ✅ POST /api/files/upload (streaming multipart)
- ✅ POST /api/files/upload/resume (resumable)
- ✅ WebSocket /api/files/upload/progress (real-time)
- ✅ Chunked upload working
- ✅ Compression для text/* content-types

**Upload Flow**:
```
Client → Ingester (chunked upload)
       → Storage Element (write file + attr.json)
       → PostgreSQL (index metadata)
       → Redis (publish event)
```

---

#### Неделя 8-9: Batch Operations & File Management

**Задачи**:
1. Реализовать batch upload (до 100 files / 1GB)
2. Реализовать file transfer между storage elements
3. Реализовать file deletion (edit mode only)
4. Реализовать Service Discovery client
5. Реализовать Circuit Breaker для storage elements
6. Написать performance tests

**Deliverables**:
- ✅ POST /api/files/batch-upload (multiple files)
- ✅ POST /api/files/:uuid/transfer (between storage elements)
- ✅ DELETE /api/files/:uuid (с валидацией mode)
- ✅ Circuit Breaker pattern для resilience
- ✅ Throughput > 50MB/s

---

### ФАЗА 4: Query Module (Недели 10-12)

**Цель**: Быстрый поиск и получение файлов

#### Неделя 10-11: Search Implementation

**Задачи**:
1. Создать структуру query-module/ проекта
2. Реализовать PostgreSQL Full-Text Search
3. Реализовать multi-level cache (Local → Redis → DB)
4. Реализовать autocomplete suggestions
5. Реализовать файловый download с streaming
6. Интеграция со всеми storage elements

**Deliverables**:
- ✅ GET /api/files/search?q=query (full-text search)
- ✅ GET /api/files/autocomplete?prefix=... (suggestions)
- ✅ GET /api/files/:uuid/download (streaming download)
- ✅ Cache hit ratio > 80%
- ✅ Search latency < 100ms (p95)

**Search Query Example**:
```sql
SELECT uuid, original_filename, username, metadata
FROM storage_elem_01_files
WHERE to_tsvector('russian', original_filename || ' ' || metadata::text)
      @@ plainto_tsquery('russian', $1)
ORDER BY ts_rank(...) DESC
LIMIT 100;
```

---

#### Неделя 12: Performance Optimization

**Задачи**:
1. Реализовать connection pooling к storage elements
2. Оптимизировать cache invalidation strategy
3. Реализовать read consistency checks
4. Добавить rate limiting
5. Провести load testing
6. Написать performance benchmarks

**Deliverables**:
- ✅ HTTP/2 connection pooling
- ✅ Cache TTL optimization
- ✅ Rate limiting (100 req/min per user)
- ✅ Load tests: 1000 concurrent searches
- ✅ Download throughput > 100MB/s

---

### ФАЗА 5: Admin UI (Недели 13-16)

**Цель**: Angular интерфейс администрирования

#### Неделя 13-14: Core UI Components

**Задачи**:
1. Создать Angular проект admin-ui/
2. Реализовать authentication module
3. Реализовать file manager component
4. Реализовать user management interface
5. Настроить routing и navigation
6. Интеграция с backend API

**Deliverables**:
- ✅ Login page с LDAP/local auth
- ✅ File upload/download UI
- ✅ File search с filters
- ✅ User CRUD interface (admin only)
- ✅ Responsive design (mobile/tablet/desktop)

**Angular Structure**:
```
admin-ui/
├── src/
│   ├── app/
│   │   ├── auth/
│   │   │   ├── login/
│   │   │   └── auth.service.ts
│   │   ├── files/
│   │   │   ├── file-list/
│   │   │   ├── file-upload/
│   │   │   └── file.service.ts
│   │   ├── users/
│   │   │   └── user-management/
│   │   └── dashboard/
│   └── environments/
```

---

#### Неделя 15-16: Dashboard & Testing

**Задачи**:
1. Реализовать system dashboard с метриками
2. Реализовать storage element monitoring
3. Добавить real-time updates (WebSocket)
4. Написать E2E tests (Playwright)
5. Провести accessibility testing (WCAG 2.1 AA)
6. Deployment в Nginx контейнер

**Deliverables**:
- ✅ Dashboard с storage utilization
- ✅ Real-time file upload progress
- ✅ Storage element status monitoring
- ✅ E2E test suite > 30 scenarios
- ✅ Accessibility compliant
- ✅ Production build deployed в Nginx

---

## MVP Scope (Недели 1-12)

### Что ВКЛЮЧЕНО в MVP:

**✅ Функциональность**:
- Аутентификация через LDAP + local fallback
- JWT токены (HS256)
- Загрузка файлов (streaming, resumable)
- Поиск файлов (PostgreSQL FTS)
- Скачивание файлов
- User management (admin)
- Storage element registry
- Базовый UI (файловый менеджер)

**✅ Компоненты**:
- Admin Module (один инстанс)
- Storage Element (один инстанс, local storage)
- Ingester Module (один инстанс)
- Query Module (один инстанс)
- Admin UI (базовый)

**✅ Инфраструктура**:
- PostgreSQL (single instance)
- Redis (single instance)
- MinIO (опционально для S3 storage)
- LDAP (389ds)
- Nginx reverse proxy

### Что НЕ ВКЛЮЧЕНО в MVP:

**❌ Отложено до Production-Ready**:
- Raft Consensus (simplified leader election через Redis)
- Saga Pattern (simplified без compensations)
- Vector Clocks (Last-Write-Wins)
- Circuit Breaker (basic retry logic)
- CDN Integration
- Kafka Integration
- Webhook System
- Batch operations API
- OpenTelemetry tracing
- Redis Cluster (standalone Redis)
- PostgreSQL репликация
- HAProxy Load Balancer
- Advanced monitoring (Prometheus + Grafana)

---

## Production-Ready Upgrades (Недели 13-24)

### Неделя 17-18: High Availability Infrastructure

**Задачи**:
1. Настроить Redis Cluster (6 nodes)
2. Настроить PostgreSQL Primary-Standby
3. Настроить HAProxy + keepalived
4. Настроить Prometheus + Grafana
5. Протестировать failover scenarios

**Deliverables**:
- ✅ Redis Cluster RTO < 30s
- ✅ PostgreSQL failover RTO < 60s
- ✅ Load Balancer VRRP failover < 5s
- ✅ Monitoring dashboards

---

### Неделя 19-20: Consistency & Resilience

**Задачи**:
1. Реализовать simplified Raft через etcd client
2. Реализовать Saga Pattern для file operations
3. Реализовать Circuit Breaker patterns
4. Реализовать automatic reconciliation
5. Написать chaos engineering tests

**Deliverables**:
- ✅ Admin Module Cluster (3 nodes)
- ✅ Saga orchestration для upload/transfer/delete
- ✅ Circuit Breaker для всех inter-service calls
- ✅ Consistency checks каждые 15 минут

---

### Неделя 21-24: Advanced Features & Testing

**Задачи**:
1. Реализовать OpenTelemetry distributed tracing
2. Добавить custom business metrics
3. Реализовать webhook system
4. Провести security testing (OWASP ZAP)
5. Провести penetration testing
6. Написать runbooks для operations

**Deliverables**:
- ✅ Jaeger UI с distributed traces
- ✅ Prometheus metrics для business KPIs
- ✅ Webhook notifications (file events)
- ✅ Security scan passed
- ✅ Operational documentation

---

## Критерии готовности по фазам

### MVP (Недели 1-12):
- ✅ Все 4 модуля запущены и работают
- ✅ E2E тесты пройдены (>80% coverage)
- ✅ Можно загрузить, найти, скачать файл
- ✅ LDAP authentication working
- ✅ Базовый UI functional
- ✅ Performance: upload >50MB/s, search <100ms

### Production-Ready (Недели 13-24):
- ✅ HA компоненты развернуты
- ✅ Failover tested (RTO < 60s)
- ✅ Consistency mechanisms работают
- ✅ Security testing passed
- ✅ Monitoring comprehensive
- ✅ Operational runbooks готовы

---

## Команды для быстрого старта

### 1. Запуск инфраструктуры:
```bash
docker-compose up -d
docker-compose ps  # проверка статуса
```

### 2. Создание первого модуля (Admin Module):
```bash
mkdir -p admin-module/app
cd admin-module

# Создать requirements.txt
cat > requirements.txt << EOF
fastapi==0.104.1
uvicorn[standard]==0.24.0
asyncpg==0.29.0
redis==5.0.1
ldap3==2.9.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
pydantic-settings==2.1.0
alembic==1.13.0
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
EOF

# Установка зависимостей
py -m pip install -r requirements.txt

# Создать базовую структуру
mkdir -p app/{auth,api,models,db,utils} tests
touch app/{__init__,main,config}.py
touch app/auth/{__init__,jwt_manager,ldap_client,dependencies}.py
touch app/api/{__init__,auth,users,storage}.py
touch app/models/{__init__,user,storage}.py
touch app/db/{__init__,database}.py
```

### 3. Первое приложение (app/main.py):
```python
from fastapi import FastAPI
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version
)

@app.get("/health/live")
async def health_live():
    return {"status": "ok"}

@app.get("/health/ready")
async def health_ready():
    # TODO: check DB, Redis, LDAP connections
    return {"status": "ready"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 4. Запуск и проверка:
```bash
py -m uvicorn app.main:app --reload --port 8000

# В другом терминале:
curl http://localhost:8000/health/live
# {"status":"ok"}
```

---

## Следующие шаги (Неделя 1)

### День 1-2: Admin Module Setup
1. ✅ Создать структуру admin-module/
2. ✅ Настроить FastAPI приложение
3. ✅ Подключиться к PostgreSQL
4. ✅ Подключиться к Redis
5. ✅ Проверить health endpoints

### День 3-4: Database Setup
1. ✅ Создать базу данных artstore_admin
2. ✅ Настроить Alembic migrations
3. ✅ Создать таблицы users и storage_elements
4. ✅ Написать первые unit tests

### День 5: LDAP Integration
1. ✅ Подключиться к LDAP (localhost:1389)
2. ✅ Написать ldap_client.py
3. ✅ Протестировать authentication
4. ✅ Создать тестовых пользователей в LDAP

---

## Заключение

План сфокусирован на **разработке приложения** с использованием существующей инфраструктуры:

**✅ Преимущества подхода**:
- Инфраструктура уже готова → старт разработки сразу
- MVP за 12 недель вместо 16 недель
- Постепенное добавление HA компонентов
- Каждая неделя имеет измеримые deliverables

**🎯 Ключевые milestone points**:
- **Неделя 3**: Admin Module готов (auth + user management)
- **Неделя 6**: Storage Element готов (файловое хранилище)
- **Неделя 9**: Ingester готов (загрузка файлов)
- **Неделя 12**: MVP готов (все компоненты работают)
- **Неделя 16**: UI готов (пользовательский интерфейс)
- **Неделя 24**: Production-Ready (HA + Security + Monitoring)

**🚀 Начинаем с Недели 1: Admin Module структура и подключения!**
