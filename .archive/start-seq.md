# Рекомендованная последовательность разработки модулей ArtStore

## 🎯 Оптимальная последовательность разработки

### **Фаза 1: Фундамент системы (критичная инфраструктура)**

#### 1️⃣ **Базовая инфраструктура** (текущее состояние: ✅ готова)
- PostgreSQL, Redis, MinIO, LDAP, DEX
- Docker Compose конфигурация
- **Статус**: Уже развернута

#### 2️⃣ **Storage Element** (Standalone режим)
**Приоритет**: 🔴 КРИТИЧНЫЙ (основа всей системы)

**Почему первым**:
- Единственный источник истины для файлов и метаданных (`*.attr.json`)
- Остальные модули зависят от Storage Element API
- Можно разрабатывать и тестировать изолированно

**Ключевые компоненты для MVP**:
```yaml
Core Features:
  ✓ File naming utility (с автоматическим обрезанием до 200 символов)
  ✓ Atomic attr.json write (WAL → temp → fsync → rename)
  ✓ Режимы: EDIT, RW, RO, AR (с переходами)
  ✓ Local filesystem storage
  ✓ PostgreSQL metadata cache
  ✓ Health checks (/health/live, /health/ready)
  ✓ Prometheus metrics

Defer for Later:
  ⏳ S3 storage support
  ⏳ Replication (опциональная функция)
  ⏳ Redis integration (для Service Discovery)
```

---

#### 3️⃣ **Admin Module Cluster** (Single node сначала)
**Приоритет**: 🔴 КРИТИЧНЫЙ (центр аутентификации)

**Почему вторым**:
- Генерирует JWT токены для Ingester/Query модулей
- Управляет пользователями и Storage Elements
- Координирует Saga транзакции

**Ключевые компоненты для MVP**:
```yaml
Core Features:
  ✓ JWT generation (RS256)
  ✓ LDAP integration (basic auth + role mapping)
  ✓ User management API
  ✓ Storage Element registration
  ✓ Health checks + Prometheus metrics
  ✓ Saga Orchestrator (базовая версия для Upload/Delete)

Defer for Later:
  ⏳ Raft consensus кластер (можно начать с single node)
  ⏳ Automated JWT key rotation (manual первые версии)
  ⏳ Webhook management
  ⏳ Batch operations API
```

---

### **Фаза 2: Операционные модули (работа с файлами)**

#### 4️⃣ **Ingester Module**
**Приоритет**: 🟡 ВАЖНЫЙ (основная функциональность)

**Почему третьим**:
- Требует работающий Admin Module (JWT validation)
- Требует работающий Storage Element (file storage)
- Позволяет начать загрузку файлов

**Ключевые компоненты для MVP**:
```yaml
Core Features:
  ✓ File upload (single file, streaming)
  ✓ JWT token validation (RS256 public key)
  ✓ Saga participant (Upload operation)
  ✓ Basic file validation (size, type)
  ✓ Health checks + Prometheus metrics

Defer for Later:
  ⏳ Parallel processing (множественные файлы)
  ⏳ Compression on-the-fly (Brotli/GZIP)
  ⏳ CDN pre-upload
  ⏳ Kafka integration
  ⏳ Resumable uploads
  ⏳ Batch upload API
```

---

#### 5️⃣ **Query Module**
**Приоритет**: 🟡 ВАЖНЫЙ (поиск и доступ к файлам)

**Почему четвертым**:
- Требует работающий Admin Module (JWT validation)
- Требует работающий Storage Element (file retrieval)
- Требует PostgreSQL metadata cache (для поиска)

**Ключевые компоненты для MVP**:
```yaml
Core Features:
  ✓ File search (PostgreSQL full-text search через GIN индексы)
  ✓ File download (single file)
  ✓ JWT token validation
  ✓ Health checks + Prometheus metrics

Defer for Later:
  ⏳ Multi-level caching (Redis + Local cache)
  ⏳ CDN integration
  ⏳ Connection pooling (HTTP/2)
  ⏳ Resumable downloads
  ⏳ Digital signature verification
  ⏳ Real-time search suggestions
```

---

### **Фаза 3: UI и Advanced Features**

#### 6️⃣ **Admin UI** (Angular)
**Приоритет**: 🟢 ЖЕЛАТЕЛЬНЫЙ (удобство управления)

**Почему последним в основной разработке**:
- Требует работающие API всех модулей
- Не блокирует функциональность (можно использовать Postman/curl)
- Можно разрабатывать итеративно

**Ключевые компоненты для MVP**:
```yaml
Core Features:
  ✓ Login form (LDAP authentication)
  ✓ File upload interface
  ✓ File search interface
  ✓ Storage Element management (list, create)
  ✓ User management (basic CRUD)

Defer for Later:
  ⏳ Dashboard с статистикой
  ⏳ LDAP attribute mapping UI
  ⏳ Webhook configuration
  ⏳ Batch operations UI
  ⏳ Advanced search filters
```

---

### **Фаза 4: Enterprise Features (постепенное улучшение)**

После завершения MVP (модули 1-6), добавлять постепенно:

```yaml
High Availability:
  ⏳ Admin Module Raft cluster (3+ nodes)
  ⏳ Redis Sentinel/Cluster (6+ nodes)
  ⏳ Load Balancer Cluster (HAProxy + keepalived)
  ⏳ Storage Element replication (опционально)

Advanced Operations:
  ⏳ Batch operations (upload/delete до 100 файлов)
  ⏳ Webhook system (restore events)
  ⏳ AR mode restore workflow
  ⏳ Automated retention management

Performance:
  ⏳ Multi-level caching (CDN → Redis → Local → DB)
  ⏳ Compression on-the-fly
  ⏳ Kafka для async processing
  ⏳ HTTP/2 connection pooling

Security:
  ⏳ Automated JWT key rotation
  ⏳ TLS 1.3 для всех соединений
  ⏳ Fine-grained RBAC
  ⏳ Comprehensive audit logging

Monitoring:
  ⏳ OpenTelemetry distributed tracing
  ⏳ Custom business metrics
  ⏳ Third-party analytics integration
```

---

## 📊 Визуальная последовательность разработки

```
┌──────────────────────────────────────────────┐
│ Фаза 1: Фундамент (4-6 недель)              │
└──────────────────────────────────────────────┘
   ┌─────────────────────┐
   │ 1. Infrastructure   │ ✅ Ready
   └─────────────────────┘
           ↓
   ┌─────────────────────┐
   │ 2. Storage Element  │ 🔴 START HERE
   └─────────────────────┘
           ↓
   ┌─────────────────────┐
   │ 3. Admin Module     │ 🔴 Critical
   └─────────────────────┘

┌──────────────────────────────────────────────┐
│ Фаза 2: Операционные модули (3-4 недели)    │
└──────────────────────────────────────────────┘
           ↓
   ┌─────────────────────┐
   │ 4. Ingester Module  │ 🟡 Important
   └─────────────────────┘
           ↓
   ┌─────────────────────┐
   │ 5. Query Module     │ 🟡 Important
   └─────────────────────┘

┌──────────────────────────────────────────────┐
│ Фаза 3: UI (2-3 недели)                     │
└──────────────────────────────────────────────┘
           ↓
   ┌─────────────────────┐
   │ 6. Admin UI         │ 🟢 Nice-to-have
   └─────────────────────┘

┌──────────────────────────────────────────────┐
│ Фаза 4: Enterprise Features (ongoing)       │
└──────────────────────────────────────────────┘
   - HA кластеры (Admin, Redis, LB)
   - Репликация Storage Elements
   - Batch operations & Webhooks
   - Advanced monitoring & security
```

---

## 🚀 Рекомендованный план старта

### **Неделя 1-2: Storage Element**
```bash
/sc:load
/sc:design "Storage Element API endpoints and file operations"
/sc:implement "File naming utility с тестами"
/sc:implement "Atomic attr.json write с WAL"
/sc:implement "Storage modes (EDIT/RW/RO/AR) с переходами"
/sc:test "Unit tests для всех file operations"
/sc:save
```

### **Неделя 3-4: Admin Module**
```bash
/sc:load
/sc:design "Admin Module REST API и JWT generation"
/sc:implement "JWT RS256 generation и validation"
/sc:implement "LDAP integration с role mapping"
/sc:implement "Storage Element registration API"
/sc:implement "Saga Orchestrator базовая версия"
/sc:save
```

### **Неделя 5-6: Ingester Module**
```bash
/sc:load
/sc:design "Ingester Module upload workflow"
/sc:implement "File upload endpoint с streaming"
/sc:implement "JWT validation интеграция"
/sc:implement "Saga participant для Upload"
/sc:test "Integration tests с Storage Element"
/sc:save
```

### **Неделя 7-8: Query Module**
```bash
/sc:load
/sc:design "Query Module search и download workflow"
/sc:implement "PostgreSQL full-text search с GIN индексами"
/sc:implement "File download endpoint"
/sc:implement "JWT validation интеграция"
/sc:test "Integration tests с Storage Element"
/sc:save
```

### **Неделя 9-11: Admin UI**
```bash
/sc:load
/sc:design "Admin UI компоненты и navigation"
/sc:implement "Login form с LDAP authentication"
/sc:implement "File upload/search interface"
/sc:implement "Storage Element management UI"
/sc:implement "User management UI"
/sc:save
```

---

## 💡 Ключевые принципы разработки

### ✅ Start Simple, Scale Later
Начинайте с standalone компонентов, добавляйте HA/кластеризацию постепенно

### ✅ Test Early
Unit + Integration тесты с первых этапов разработки

### ✅ Iterative Development
MVP → Feedback → Improvements → Repeat

### ✅ Documentation-Driven
OpenAPI specs и API документация перед написанием кода

### ✅ Security First
JWT validation, LDAP integration, audit logging с самого начала

### ✅ Dependency Management
Строго следовать последовательности: Storage Element → Admin Module → Ingester/Query → UI

---

## 📋 Checklist перед началом каждого модуля

### Before Starting Development
- [ ] Прочитать `@ARCHITECTURE_DECISIONS.md` для архитектурного контекста
- [ ] Прочитать `@CLAUDE.md` для project-specific инструкций
- [ ] Запустить `/sc:load` для загрузки session context
- [ ] Создать feature branch: `git checkout -b feature/module-name`

### During Development
- [ ] Использовать `/sc:design` для проектирования API/компонентов
- [ ] Использовать `/sc:implement` для написания кода
- [ ] Писать unit tests параллельно с кодом
- [ ] Использовать `/sc:test` для генерации и запуска тестов
- [ ] Документировать API через OpenAPI/Swagger

### Before Completing Module
- [ ] Запустить все тесты: `pytest tests/ -v --cov`
- [ ] Проверить code coverage (target: >80%)
- [ ] Обновить README.md модуля с примерами использования
- [ ] Запустить `/sc:save` для сохранения session state
- [ ] Создать PR: `/sc:git "создать PR для модуля"`

---

## 🎯 Критерии готовности модуля (Definition of Done)

### Code Quality
- [ ] Все unit tests проходят успешно
- [ ] Code coverage >= 80%
- [ ] Нет критичных issues от linter (pylint, mypy)
- [ ] Все TODO комментарии разрешены или задокументированы

### Functionality
- [ ] Все core features из MVP реализованы
- [ ] Health checks (/health/live, /health/ready) работают
- [ ] Prometheus metrics endpoint доступен
- [ ] API документация (OpenAPI) актуальна

### Integration
- [ ] Integration tests с зависимыми модулями проходят
- [ ] Docker container собирается без ошибок
- [ ] Модуль запускается через docker-compose
- [ ] Логирование настроено (structured JSON logs)

### Documentation
- [ ] README.md обновлен с примерами использования
- [ ] API endpoints задокументированы
- [ ] Configuration options описаны
- [ ] Troubleshooting guide добавлен

---

## 🔄 Workflow для каждой сессии разработки

```bash
# 1. Начало сессии
/sc:load  # Загрузить контекст проекта

# 2. Проверить текущее состояние
git status
git branch  # Убедиться, что на feature branch

# 3. Работа над модулем
/sc:design "компонент или API"
/sc:implement "функция или endpoint"
/sc:test "создать тесты для компонента"

# 4. Проверка качества
pytest tests/ -v --cov
pylint app/

# 5. Завершение сессии
/sc:save  # Сохранить прогресс
git add .
git commit -m "descriptive message"
```

---

## 📚 Полезные ресурсы

### Документация проекта
- [ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) - Архитектурные решения
- [CLAUDE.md](../CLAUDE.md) - Инструкции для разработки
- [README.md](../README.md) - Обзор проекта

### Технологический стек
- **Backend**: Python 3.12, FastAPI, SQLAlchemy, Pydantic
- **Database**: PostgreSQL 16, Redis 7
- **Storage**: Local filesystem, MinIO (S3-compatible)
- **Auth**: LDAP/AD, JWT (RS256)
- **Frontend**: Angular 17, TypeScript
- **Monitoring**: Prometheus, OpenTelemetry
- **Deployment**: Docker, docker-compose

### Полезные команды SuperClaude
- `/sc:load` - Загрузить session context
- `/sc:save` - Сохранить session state
- `/sc:design` - Спроектировать компонент
- `/sc:implement` - Реализовать функциональность
- `/sc:test` - Создать и запустить тесты
- `/sc:analyze` - Анализ кода
- `/sc:improve` - Улучшить код
- `/sc:git` - Git операции

---

## 🚦 Текущий статус разработки

| Модуль | Приоритет | Статус | Прогресс |
|--------|-----------|--------|----------|
| Infrastructure | ✅ Ready | Завершено | 100% |
| Storage Element | 🔴 Critical | Не начато | 0% |
| Admin Module | 🔴 Critical | Не начато | 0% |
| Ingester Module | 🟡 Important | Не начато | 0% |
| Query Module | 🟡 Important | Не начато | 0% |
| Admin UI | 🟢 Nice-to-have | Не начато | 0% |

**Следующий шаг**: Начать разработку Storage Element 🚀

---

*Документ создан: 2025-11-08*
*Последнее обновление: 2025-11-08*
