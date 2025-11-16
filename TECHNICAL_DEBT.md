# Технологический долг ArtStore

Этот файл отслеживает известные технические долги, требующие устранения в будущем.

## Формат записи

```markdown
### [ПРИОРИТЕТ] Название задачи
**Модуль**: название модуля
**Дата добавления**: YYYY-MM-DD
**Оценка сложности**: низкая/средняя/высокая
**Описание**: Подробное описание проблемы
**План устранения**: Шаги для решения
**Связанные файлы**: Список затронутых файлов
```

---

## 🔴 Критический долг

### [CRITICAL] SQLAlchemy Table Prefix Configuration

**Модуль**: storage-element
**Дата добавления**: 2025-11-14 (Sprint 6)
**Оценка сложности**: средняя
**Приоритет**: P0 (blocks 16 integration tests)

**Описание**:
SQLAlchemy models используют f-strings для генерации `__tablename__` на уровне class definition (import time):
```python
class FileMetadata(Base):
    __tablename__ = f"{settings.database.table_prefix}_files"  # Evaluated at import!
```

**Проблема**:
1. Models импортируются при `from app.models import FileMetadata`
2. `__tablename__` evaluates f-string IMMEDIATELY с текущим `settings.database.table_prefix`
3. В production: `settings.database.table_prefix = "storage_elem_01"` (default из config.py:85)
4. Test environment: `os.environ["DB_TABLE_PREFIX"] = "test_storage"` устанавливается в conftest.py AFTER imports
5. Result: Models look for `storage_elem_01_*` tables, но Alembic создал `test_storage_*` tables

**Impact**:
- 16/39 integration tests failing с ошибкой: `ERROR: relation "storage_elem_01_wal" does not exist`
- Test environment configuration не работает
- Невозможно запустить integration tests для валидации кода

**Attempted Fixes (ALL FAILED)**:
1. ✗ `os.environ.setdefault()` → Too late, models уже imported
2. ✗ Direct assignment `os.environ["DB_TABLE_PREFIX"]` → Still too late
3. ✗ `importlib.reload()` → Reloads settings но models keep old `__tablename__`
4. ✗ Module reload of models → Creates duplicate classes, SQLAlchemy warnings

**Решение (Sprint 7)**:
Использовать `@declared_attr` для runtime table name resolution:
```python
from sqlalchemy.ext.declarative import declared_attr

class FileMetadata(Base):
    @declared_attr
    def __tablename__(cls):
        from app.core.config import settings
        return f"{settings.database.table_prefix}_files"
```

**План устранения**:
1. Refactor 3 model files для использования `@declared_attr`:
   - `app/models/file_metadata.py`
   - `app/models/storage_config.py`
   - `app/models/wal.py`
2. Test с production table prefix (`storage_elem_01`)
3. Test с test table prefix (`test_storage`)
4. Verify all 16 blocked tests now passing
5. Create Architecture Decision Record (ADR)

**Effort**: 2-3 hours
**Sprint**: 7

**Связанные файлы**:
- `storage-element/app/models/file_metadata.py:45`
- `storage-element/app/models/storage_config.py`
- `storage-element/app/models/wal.py:59`
- `storage-element/tests/integration/conftest.py:34`
- `storage-element/SPRINT_6_STATUS.md:62-101` (detailed analysis)

**Ссылки**:
- [SPRINT_6_STATUS.md:62](storage-element/SPRINT_6_STATUS.md#L62) - Detailed blocker analysis
- [conftest.py:34](storage-element/tests/integration/conftest.py#L34) - Table prefix configuration

---

### [CRITICAL] AsyncIO Event Loop Isolation

**Модуль**: storage-element
**Дата добавления**: 2025-11-14 (Sprint 6)
**Оценка сложности**: низкая
**Приоритет**: P0 (blocks 2 integration tests)

**Описание**:
Database cache integration tests failing с ошибкой:
```
RuntimeError: Task <Task pending> attached to a different loop
```

**Проблема**:
- pytest-asyncio fixtures используют разные event loops
- Database session fixtures не properly scoped для async tests
- Task created в одном loop, но executed в другом

**Impact**:
- 2 database cache tests failing: `test_cache_entry_created_on_upload`, `test_cache_consistency_with_attr_file`

**Решение (Sprint 7)**:
Proper async fixture scoping:
```python
# conftest.py
@pytest.fixture(scope="function")
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()  # Cleanup after each test
```

**План устранения**:
1. Update database session fixtures в `conftest.py`
2. Ensure proper async scope isolation
3. Verify both database cache tests pass
4. Add documentation для async testing best practices

**Effort**: 1 hour
**Sprint**: 7

**Связанные файлы**:
- `storage-element/tests/integration/conftest.py` (session fixtures)
- `storage-element/tests/integration/test_storage_service.py` (failing tests)
- `storage-element/SPRINT_6_STATUS.md:223` (technical debt)

---

### [CRITICAL] Миграция логирования на JSON формат

**Модуль**: Все модули
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя

**Описание**:
- Все production логи ДОЛЖНЫ быть в JSON формате для интеграции с ELK Stack, Splunk и другими системами анализа
- Текущее состояние: некоторые модули используют text формат
- JSON формат обязателен для production, text разрешен только в development режиме

**План устранения**:
1. Проверить все модули на использование JSON логирования
2. Обновить конфигурацию logging во всех модулях:
   - `LOG_FORMAT=json` для production (docker-compose.yml)
   - `LOG_FORMAT=text` только для development (docker-compose.dev.yml)
3. Обеспечить обязательные поля в логах:
   - timestamp, level, logger, message, module, function, line
   - request_id, user_id, trace_id (для OpenTelemetry интеграции)
4. Использовать python-json-logger или аналоги для structured logging
5. Добавить валидацию формата логов в CI/CD pipeline

**Связанные файлы**:
- `admin-module/app/core/logging_config.py`
- `storage-element/app/core/logging_config.py`
- `ingester-module/app/core/logging_config.py`
- `query-module/app/core/logging_config.py`
- Все `docker-compose.yml` файлы
- `CLAUDE.md` (требования к логированию)

**Ссылки**:
- [CLAUDE.md:53-63](CLAUDE.md#L53-L63) - Требования к логированию

---

### [CRITICAL] LDAP Infrastructure Removal (CANCELLED)

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Status**: ❌ CANCELLED (Architecture change 2025-01-12)
**Оценка сложности**: N/A

**Описание**:
~~Отсутствует LDIF файл с базовой структурой LDAP хранилища для ArtStore~~

**Причина отмены**:
Требования от заказчика изменились (2025-01-12):
- Система предназначена для M2M (machine-to-machine) authentication
- Service Accounts вместо human users
- OAuth 2.0 Client Credentials вместо LDAP
- LDAP infrastructure будет удалена в Sprint 11 (Phase 4, Week 11-12)

**Ссылки**:
- [DEVELOPMENT_PLAN.md:220-236](DEVELOPMENT_PLAN.md#L220-L236) - Architecture change
- [DEVELOPMENT_PLAN.md:368-378](DEVELOPMENT_PLAN.md#L368-L378) - LDAP removal Sprint 11

---

## 🟡 Важный долг

### [HIGH] StorageService API Mismatch

**Модуль**: storage-element
**Дата добавления**: 2025-11-14 (Sprint 6)
**Оценка сложности**: низкая
**Приоритет**: P1 (blocks 6 integration tests)

**Описание**:
Integration tests используют старый API LocalStorageService который не существует:
```python
# OLD API (doesn't exist):
stored_path = await storage_service.store_file(file_data=..., storage_filename=...)
checksum = await storage_service.calculate_checksum(file_path)

# CURRENT API:
size, checksum = await storage_service.write_file(relative_path=..., file_data=...)
```

**Impact**:
- 6 storage service tests failing с `AttributeError: 'LocalStorageService' object has no attribute 'store_file'`
- Cannot validate storage service functionality
- API evolution не reflected в tests

**Решение (Sprint 7)**:
Update integration tests для использования current API:
```python
# Updated test pattern:
size, checksum = await storage_service.write_file(
    relative_path=storage_filename,
    file_data=file_content
)
# checksum уже returned, не нужен separate call
```

**План устранения**:
1. Update `test_storage_service.py` для использования `write_file()` API
2. Remove calls к non-existent `calculate_checksum()` method
3. Update test assertions для new return format (size, checksum tuple)
4. Verify all 6 storage service tests pass
5. Document current API в integration test README

**Effort**: 1-2 hours
**Sprint**: 7

**Связанные файлы**:
- `storage-element/tests/integration/test_storage_service.py` (failing tests)
- `storage-element/app/services/storage_service.py` (current API)
- `storage-element/SPRINT_6_STATUS.md:218-221` (technical debt)

---

### [HIGH] datetime.utcnow() Project Audit

**Модуль**: storage-element, admin-module
**Дата добавления**: 2025-11-14 (Sprint 6)
**Оценка сложности**: низкая
**Приоритет**: P2 (risk mitigation)

**Описание**:
`datetime.utcnow()` deprecated и создает timezone-naive datetimes, что приводит к bugs на timezone-aware systems.

**Fixed occurrences (Sprint 5-6)**:
- ✅ `tests/utils/jwt_utils.py` - JWT token generation (Sprint 5)
- ✅ `app/services/wal_service.py` - WAL entry timestamps (Sprint 5)
- ✅ `app/services/file_service.py` - File creation timestamps (Sprint 6, 3 occurrences)

**Risk**:
- Potentially more occurrences в untested code paths
- Risk of timezone bugs в production если не audited

**Correct pattern**:
```python
# WRONG (deprecated, timezone-naive):
datetime.utcnow()

# CORRECT (timezone-aware UTC):
from datetime import datetime, timezone
datetime.now(timezone.utc)
```

**План устранения (Sprint 7)**:
1. Project-wide grep для remaining `datetime.utcnow()` occurrences:
   ```bash
   grep -r "datetime.utcnow()" storage-element/app/ admin-module/app/
   ```
2. Replace all occurrences с `datetime.now(timezone.utc)`
3. Add linting rule (pylint/flake8) для prevent regression:
   ```python
   # .pylintrc or pyproject.toml
   [tool.pylint.messages_control]
   disable = ["datetime-utcnow-deprecated"]
   ```
4. Document pattern в development guide

**Effort**: 30 minutes
**Sprint**: 7

**Связанные файлы**:
- `storage-element/app/services/file_service.py:139,573,597` (fixed Sprint 6)
- `storage-element/tests/utils/jwt_utils.py` (fixed Sprint 5)
- `storage-element/app/services/wal_service.py` (fixed Sprint 5)
- Potentially: other files not yet audited

**Ссылки**:
- [SPRINT_6_STATUS.md:229](storage-element/SPRINT_6_STATUS.md#L229) - Technical debt
- [SPRINT_5_REPORT.md:84-99](storage-element/SPRINT_5_REPORT.md#L84-L99) - Sprint 5 fixes

---

### [HIGH] Initial Admin Auto-Creation (COMPLETED)

**Модуль**: admin-module
**Дата добавления**: 2025-01-11
**Status**: ✅ COMPLETED (Sprint 3, 2025-01-13)
**Оценка сложности**: средняя

**Описание**:
~~При первом запуске системы необходимо автоматически создавать администратора для начальной настройки~~

**Completion Summary**:
- ✅ Initial Admin service account auto-creation implemented (Sprint 3)
- ✅ Configurable via environment variables (`INITIAL_ADMIN_*`)
- ✅ Protection against deletion (`is_system=True` flag)
- ✅ Production-ready с proper bcrypt hashing

**Implementation Details**:
- Auto-created on first startup если в БД нет service accounts
- Configurable: name, client_id, client_secret, role
- System flag prevents accidental deletion
- Documented в CLAUDE.md Testing Credentials

**Связанные файлы**:
- `admin-module/app/core/config.py` - InitialAdminSettings
- `admin-module/app/db/init_db.py` - create_initial_admin()
- `admin-module/app/main.py` - lifespan integration
- `admin-module/tests/unit/test_initial_admin.py` - tests

**Ссылки**:
- [DEVELOPMENT_PLAN.md:88-92](DEVELOPMENT_PLAN.md#L88-L92) - Sprint 3 achievement
- [CLAUDE.md](CLAUDE.md) - Testing Credentials updated

---

### [HIGH] API Endpoint Integration Tests

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя

**Описание**:
- API endpoint tests в `test_auth_integration.py` требуют dependency injection для test database
- Текущее состояние: 3 из 9 API tests падают из-за использования production database
- AuthService integration tests все проходят (13/13)

**План устранения**:
1. Создать dependency override для database session в API tests
2. Использовать `app.dependency_overrides` для подмены get_db
3. Настроить AsyncClient для работы с test event loop
4. Исправить проблему "Event loop is closed" при teardown
5. Добавить фикстуру для автоматической подмены dependencies

**Связанные файлы**:
- `admin-module/tests/integration/test_auth_integration.py` (TestAuthAPIEndpoints)
- `admin-module/tests/conftest.py` (client fixture)
- `admin-module/app/api/dependencies.py`

**Статус**: 6/9 API endpoint tests проходят, 3 требуют доработки

---

### [HIGH] Password Reset Implementation

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя

**Описание**:
- Методы `create_password_reset_token` и `reset_password` возвращают заглушки
- Нужна реализация через Redis с TTL для токенов
- Требуется email отправка с токеном сброса

**План устранения**:
1. Создать Redis-based token storage с TTL (15 минут)
2. Интегрировать email service (SMTP)
3. Создать endpoint для инициации сброса пароля
4. Создать endpoint для валидации токена и установки нового пароля
5. Добавить rate limiting для prevent abuse
6. Написать integration tests

**Связанные файлы**:
- `admin-module/app/services/auth_service.py:258-314`
- Создать: `admin-module/app/services/email_service.py`
- Обновить: `admin-module/app/api/v1/endpoints/auth.py`

---

## 🟢 Средний приоритет

### [MEDIUM] pytest-asyncio Dependency

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: низкая

**Описание**:
- `pytest-asyncio` установлен в runtime, но отсутствует в requirements.txt
- Может вызвать проблемы при CI/CD или на других машинах

**План устранения**:
1. Добавить `pytest-asyncio>=1.3.0` в `requirements.txt` или `requirements-dev.txt`
2. Документировать в README.md необходимость установки dev dependencies
3. Обновить CI/CD pipeline для установки test dependencies

**Связанные файлы**:
- `admin-module/requirements.txt` или создать `requirements-dev.txt`
- `admin-module/README.md`
- `.github/workflows/tests.yml` (если есть CI)

---

## ⚪ Низкий приоритет

### [LOW] Test Coverage для API Endpoints

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя

**Описание**:
- API endpoint tests покрывают только базовый happy path и простые error cases
- Отсутствуют тесты для edge cases (expired tokens, concurrent requests, rate limiting)
- Нет performance tests для authentication endpoints

**План устранения**:
1. Добавить edge case tests:
   - Concurrent login attempts
   - Token refresh race conditions
   - Session hijacking scenarios
2. Добавить security tests:
   - SQL injection attempts
   - JWT tampering
   - Brute force protection
3. Добавить performance tests:
   - Load testing для /login endpoint
   - Stress testing для token validation

**Связанные файлы**:
- `admin-module/tests/integration/test_auth_integration.py`
- Создать: `admin-module/tests/security/`
- Создать: `admin-module/tests/performance/`

---

### [LOW] Docker Healthcheck Enhancement

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: низкая

**Описание**:
- Healthcheck только проверяет `/health/live` endpoint
- Не проверяет готовность dependencies (PostgreSQL, Redis)
- Start period увеличен до 40s как временное решение

**План устранения**:
1. Добавить `/health/ready` endpoint с проверкой dependencies
2. Использовать `/health/ready` в HEALTHCHECK
3. Уменьшить start-period обратно до разумных значений
4. Добавить dependency checks в health endpoint

**Связанные файлы**:
- `admin-module/Dockerfile:59-61`
- `admin-module/app/api/v1/endpoints/health.py`

---

## Процесс работы с техническим долгом

### Добавление нового долга
1. Добавить запись в соответствующий раздел по приоритету
2. Заполнить все обязательные поля
3. Указать оценку сложности и связанные файлы
4. Сделать commit: `docs: add technical debt - [название]`

### Устранение долга
1. Создать feature branch: `debt/название-долга`
2. Реализовать решение согласно плану устранения
3. Обновить статус в этом файле (COMPLETED) или удалить запись
4. Сделать commit: `fix: resolve technical debt - [название]`

### Приоритезация
- 🔴 **CRITICAL (P0)**: Блокирует production deployment или критические функции
- 🟡 **HIGH (P1)**: Важно для качества, но не блокирует работу
- 🟢 **MEDIUM (P2)**: Улучшения качества кода и maintainability
- ⚪ **LOW (P3)**: Nice to have, можно отложить

### Ревью долга
- Еженедельный ревью новых долгов на team meeting
- Ежемесячный ревью приоритетов существующих долгов
- Квартальная цель: устранение минимум 50% CRITICAL и HIGH долгов

---

## Статистика технологического долга

### По приоритетам
- 🔴 **CRITICAL**: 4 (3 active + 1 cancelled)
- 🟡 **HIGH**: 4 (2 active + 1 completed + 1 planned for Sprint 7)
- 🟢 **MEDIUM**: 1
- ⚪ **LOW**: 2

### По статусу
- ✅ **COMPLETED**: 1 (Initial Admin Auto-Creation)
- ❌ **CANCELLED**: 1 (LDAP Infrastructure)
- ⏳ **IN PROGRESS**: 3 (Sprint 6 → Sprint 7)
- 📋 **PLANNED**: 7

### По модулям
- **storage-element**: 4 (3 CRITICAL + 1 HIGH)
- **admin-module**: 5 (1 CRITICAL + 2 HIGH + 2 LOW)
- **Все модули**: 1 (1 CRITICAL - JSON logging)

---

**Последнее обновление**: 2025-11-16 (Sprint 16 Phase 5 Complete)
**Общее количество долгов**: 12 (4 CRITICAL, 4 HIGH, 1 MEDIUM, 2 LOW, 1 CANCELLED)
**Следующий ревью**: Sprint 17 planning

## Sprint 16 Phase 1-5 Update Summary (2025-11-16)

**Achievements - Complete Security Hardening**:

### Phase 1: Quick Security Wins ✅
- ✅ **CORS Whitelist Configuration** (All 4 Modules)
  - Enhanced CORSSettings with 3 validators (admin-module/app/core/config.py)
  - Explicit headers instead of wildcards (admin-module/app/main.py)
  - Preflight caching optimization (max_age=600)
  - Standardized CORS logging across all modules
  - Deployed: admin-module, storage-element, ingester-module, query-module

- ✅ **Strong Random Password Infrastructure**
  - PasswordPolicy class with NIST-compliant rules (admin-module/app/core/password_policy.py)
  - PasswordValidator, PasswordGenerator, PasswordHistory, PasswordExpiration
  - ServiceAccountService integration with password history enforcement
  - Cryptographically secure generation using `secrets` module (CSPRNG)
  - Database migration applied (alembic/versions/20251116_1630_add_password_policy_fields.py)
  - New fields: `secret_history` (JSONB), `secret_changed_at` (DateTime TZ)
  - Password reuse prevention (last 5 passwords tracked)

### Phase 4: TLS 1.3 + mTLS Infrastructure ✅
- ✅ **Certificate Infrastructure**: CA, server certs (4), client certs (3)
- ✅ **TLS 1.3 Configuration**: All modules configured for TLS 1.3 only
- ✅ **mTLS Middleware**: Client certificate validation with CN whitelisting
- ✅ **HTTP Client Integration**: httpx SSL context for inter-service mTLS
- ✅ **Docker Compose Deployment**: docker-compose.tls.yml for production

### Phase 5: TLS Integration Tests ✅ (NEW)
- ✅ **Test Coverage: 85+ integration tests** across all microservices
  - Admin Module: 25+ tests (test_tls_connections.py)
  - Storage Element: 20+ tests (test_tls_server.py)
  - Ingester Module: 20+ tests (test_mtls_storage_communication.py)
  - Query Module: 25+ tests (test_mtls_storage_download.py)

- ✅ **Test Categories**:
  - Certificate validation (20+ tests)
  - TLS protocol enforcement (15+ tests)
  - mTLS authentication (20+ tests)
  - Cipher suite validation (8+ tests)
  - Performance testing (12+ tests)
  - Error handling (15+ tests)
  - Integration flows (10+ tests)

- ✅ **Test Infrastructure**:
  - Docker Compose test environment (docker-compose.tls-test.yml)
  - Isolated services (separate ports: 5433, 6380, 9001)
  - Health checks for all dependencies
  - Mock services for integration testing

- ✅ **Documentation**:
  - TLS_TESTING_GUIDE.md (700+ lines) - comprehensive testing guide
  - TLS_TESTS_SUMMARY.md (500+ lines) - implementation summary
  - Quick start instructions and troubleshooting

**Security Score Improvement**: 6/10 → 9/10 (Sprint 14 baseline → Sprint 16 complete)

**Code Metrics**:
- **Files created**: 9 total
  - Phase 1: 2 (password_policy.py, migration)
  - Phase 4: 4 (generate-certs.sh, tls_middleware.py, docker-compose.tls.yml, README.md)
  - Phase 5: 7 (4 test files, docker-compose.tls-test.yml, 2 documentation files)
- **Files modified**: 19 (config, main, service, models across 4 modules)
- **Lines added**: ~6,000+ total
  - Phase 1: ~1,200 lines
  - Phase 4: ~1,800 lines
  - Phase 5: ~3,000 lines (test code + documentation)
- **Test files**: ~2,600 lines of integration tests
- **Documentation**: ~1,200 lines of comprehensive guides

**Impact on Technical Debt**:
- ✅ **CORS security debt** - RESOLVED (wildcard origins eliminated)
- ✅ **Password weakness debt** - RESOLVED (NIST-compliant policy enforced)
- ✅ **TLS encryption debt** - RESOLVED (TLS 1.3 + mTLS implemented)
- ✅ **Testing debt** - RESOLVED (comprehensive TLS test coverage)
- ✅ **Documentation debt** - RESOLVED (production-ready guides)
- CRITICAL and HIGH priority items remain from Sprint 6-7 (Storage Element blockers)
- Security infrastructure complete for production deployment

**Next Steps (Sprint 17+)**:
- Admin UI Angular interface
- Custom Business Metrics (file ops, search performance)
- Performance Optimization (CDN integration, caching improvements)

## Sprint 15 Update Summary

**Achievements**:
- ✅ **Security Hardening Phase 2-3 Complete**
  - JWT Key Rotation automated (admin-module/app/services/jwt_rotation_service.py)
  - Comprehensive Audit Logging operational (admin-module/app/services/audit_service.py)
  - Platform-Agnostic Secret Management implemented (admin-module/app/core/secrets.py)
  - Deployment examples for Docker Compose, Kubernetes, file-based secrets

**Impact on Technical Debt**:
- No existing debt items resolved in Sprint 15 (focus was on new security features)
- CRITICAL and HIGH priority items remain from Sprint 6-7 (Storage Element integration test blockers)
- New security infrastructure added but no legacy debt addressed

**Focus**:
Sprint 15 focused on building NEW security capabilities rather than resolving existing technical debt.
Sprint 16 Phase 1 addressed deferred security quick wins (CORS, passwords).
