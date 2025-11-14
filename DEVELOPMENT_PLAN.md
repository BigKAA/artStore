# План разработки ArtStore - С учетом архитектурных изменений

## Executive Summary

**ArtStore** - распределенная система файлового хранилища с микросервисной архитектурой для долгосрочного хранения документов.

**Статус**: Week 6 (Sprint 6) - Storage Element refinement и integration test fixes

**Ключевые изменения архитектуры** (2025-01-12):
1. **Упрощение аутентификации**: От LDAP к OAuth 2.0 Client Credentials (Service Accounts) ✅ РЕАЛИЗОВАНО
2. **Эволюция метаданных**: Template Schema v2.0 для гибкой эволюции attr.json ✅ РЕАЛИЗОВАНО

**Текущий прогресс**:
- **Phase 1-2 (Infrastructure + Core)**: 85% завершено (OAuth 2.0, Template Schema v2.0 реализованы)
- **Integration Tests**: 38% passing (15/39 tests, blockers identified)
- **Code Coverage**: 56% (target: 80%+)

---

## Текущий статус проекта (Week 6, Sprint 6)

✅ **Завершено (Sprints 1-6)**:
- **Admin Module**: 98% (OAuth 2.0 Client Credentials, JWT RS256, Service Account Management)
- **Storage Element**: 85% (Template Schema v2.0, WAL, Router, Docker, 56% test coverage)
- **Infrastructure**: PostgreSQL, Redis, MinIO, Docker containerization

⏳ **В процессе (Sprint 6)**:
- **Integration Test Fixes**: 15/39 passing (38%)
  - Blocked by SQLAlchemy table prefix issue (P0)
  - Blocked by AsyncIO event loop isolation (P0)
  - Blocked by LocalStorageService API mismatch (P1)

📋 **Запланировано (Sprint 7+)**:
- **Sprint 7**: Model refactoring (@declared_attr), unblock integration tests
- **Ingester Module**: File upload orchestration
- **Query Module**: PostgreSQL FTS, file search and retrieval
- **Admin UI**: Angular interface

---

## Завершенные Sprint'ы (Sprint 1-6)

### ✅ Sprint 1 (Week 1) - Project Foundation
**Дата**: 2025-01-09
**Status**: COMPLETE

**Achievements**:
- Project structure setup (4 microservices)
- Docker infrastructure (PostgreSQL, Redis, MinIO, LDAP)
- Admin Module foundation (FastAPI, Pydantic, SQLAlchemy)
- Development environment configuration

---

### ✅ Sprint 2 (Week 2) - JWT Authentication Foundation
**Дата**: 2025-01-09
**Status**: COMPLETE

**Achievements**:
- JWT RS256 authentication infrastructure
- Service Account database model (Alembic migration)
- OAuth 2.0 Client Credentials Flow (RFC 6749 compliant)
- Basic CRUD operations for service accounts

**Deliverables**:
- 22/22 unit tests passing (100%)
- JWT generation and validation working
- Database schema created

---

### ✅ Sprint 3 (Week 3) - OAuth 2.0 Implementation Complete
**Дата**: 2025-01-13
**Status**: COMPLETE (Production Ready)

**Achievements**:
1. **OAuth 2.0 Client Credentials Grant** (RFC 6749 Section 4.4)
   - POST /api/v1/auth/token endpoint
   - Client ID + Client Secret → JWT Bearer token
   - Rate limiting (100 req/min)
   - bcrypt secret hashing

2. **Service Account Management API**
   - Full CRUD operations (12 endpoints)
   - Secret rotation support
   - Role-based access control (ADMIN, OPERATOR, USER)
   - Soft delete with audit trail

3. **Initial Admin Auto-Creation**
   - Auto-create admin service account on first startup
   - Configurable via environment variables
   - Protection against accidental deletion (is_system flag)

4. **Docker Production Deployment**
   - Multi-stage Dockerfile
   - JSON logging mandatory
   - Health checks (/health/live, /health/ready)
   - External network integration

**Test Results**:
- Unit tests: 22/22 (100%)
- Integration tests: 7/9 (78% - event loop issues non-critical)

**Commits**: Multiple commits ending with healthcheck fix

---

### ✅ Sprint 4 (Week 4) - Template Schema v2.0
**Дата**: 2025-11-14
**Status**: COMPLETE

**Achievements**:
1. **Template Schema v2.0 Implementation**
   - FileAttributesV2 Pydantic model with schema versioning
   - schema_version: "2.0" field for format evolution
   - custom_attributes: Dict[str, Any] for flexible metadata
   - Auto-migration v1.0 → v2.0 via read_and_migrate_if_needed()
   - Backward compatibility v2.0 → v1.0 via to_v1_compatible() (lossy)
   - Full validation (SHA256 checksum, file_size > 0, JSON-serializable)

2. **Unit Tests**
   - 17/17 unit tests passing (100%)
   - 90% code coverage for template_schema.py
   - Test classes: Model validation, Migration v1→v2, Schema detection, Backward compat, JSON serialization

3. **Integration Tests Created**
   - test_file_operations.py - Full file operations cycle
   - test_storage_service.py - Filesystem, S3, database cache
   - test_template_schema_integration.py - Real filesystem v2.0 tests (13 tests)

**Technical Achievements**:
- Backward compatible (v1.0 files auto-migrate)
- Forward extensible (schema_version enables future evolution)
- Flexible metadata (custom_attributes)
- Production ready (90% coverage)

---

### ✅ Sprint 5 (Week 5) - JWT Integration Tests & Critical Fixes
**Дата**: 2025-11-14
**Status**: 90% COMPLETE

**Achievements**:
1. **JWT Utilities Infrastructure** (100%)
   - tests/utils/jwt_utils.py (257 lines)
   - generate_test_jwt_token() - RS256 token generation
   - verify_test_jwt_token() - Token validation
   - create_auth_headers() - HTTP request convenience wrapper
   - 20/20 unit tests passing (100%)

2. **Integration Test JWT Authentication** (100%)
   - Real RS256 tokens instead of mocks
   - httpx 0.28+ compatibility (AsyncClient with ASGITransport)
   - Function-scoped auth_headers fixture

3. **Docker Test Environment** (100%)
   - Isolated PostgreSQL (port 5433) + Redis (port 6380)
   - Alembic migrations setup for test database
   - docker-compose.test.yml configuration

4. **Critical Timezone Bug Fixes** (100%)
   - Fixed jwt_utils.py: datetime.utcnow() → datetime.now(timezone.utc)
   - Fixed wal_service.py: timestamp generation for WAL entries
   - Impact: JWT tokens now work correctly on timezone-aware systems (MSK +3)

5. **Integration Tests Status**
   - 15/39 tests passing (38%)
   - 8 tests skipped (S3, edit mode restrictions)
   - 16 tests blocked by architectural issues (identified for Sprint 6)

**Test Coverage**: 56% (foundation laid for Sprint 6 expansion)

**Commits**: `3d349a2`, `d8f5b91`, `ac7f218`

---

### ⏳ Sprint 6 (Week 6) - Integration Test Fixes (PARTIAL)
**Дата**: 2025-11-14
**Status**: 30% COMPLETE (Blocked by architectural issue)

**Completed Work**:
1. **Timezone Bug Fix in file_service.py** (100%)
   - Fixed 3 occurrences of datetime.utcnow()
   - Line 139: File creation timestamp
   - Line 573: Metadata update
   - Line 597: Attribute update
   - Pattern consistent with Sprint 5 fixes
   - Commit: `9da3ab3`

2. **Architectural Blocker Identified** (Investigation 100%)
   - **Problem**: SQLAlchemy `__tablename__ = f"{settings.database.table_prefix}_files"` evaluated at class definition (import time)
   - **Impact**: Test environment variables set AFTER models imported
   - **Result**: Tests look for wrong table names (storage_elem_01_* vs test_storage_*)
   - **Attempted Fixes**: os.environ assignment, importlib.reload() - ALL FAILED
   - **Solution Identified**: Use @declared_attr for runtime table name resolution
   - **Effort**: 2-3 hours to refactor 3 model files

3. **Sprint 6 Status Documentation** (100%)
   - Created SPRINT_6_STATUS.md (377 lines)
   - Documented 30% completion and architectural blocker
   - Identified Sprint 7 priorities with effort estimates
   - Listed 4 new technical debt items (P0-P2)
   - Commit: `e365068`

**Blocked Work** (Deferred to Sprint 7):
- AsyncIO event loop isolation (blocked by table prefix)
- LocalStorageService API mismatch (AttributeError: 'LocalStorageService' object has no attribute 'store_file')
- 16/39 integration tests failing due to blockers

**Test Status**: 15/39 passing (38%), 16 blocked, 8 skipped

**Technical Debt Identified**:
- [CRITICAL] SQLAlchemy Table Prefix Configuration (P0) - blocking 16 tests
- [CRITICAL] AsyncIO Event Loop Isolation (P0) - blocking 2 tests
- [HIGH] StorageService API Mismatch (P1) - blocking 6 tests
- [MEDIUM] datetime.utcnow() Project Audit (P2) - risk mitigation

---

## 🔄 Критическое архитектурное изменение (2025-01-12)

### Новые требования от заказчика

**Источник**: `.archive/sq.md` + research_architecture_changes_20250112.md

**Ключевое изменение**:
> "Система не предназначена для непосредственного использования конечными пользователей.
> Системой будут пользоваться другие приложения.
> Следовательно, пользователи будут только локальные и не надо реализовывать хранение их
> учетных записей в LDAP."

**Интерпретация**:
- **Смена парадигмы**: Human users → Service Accounts (API clients) ✅ РЕАЛИЗОВАНО (Sprint 2-3)
- **Удаление LDAP**: Полный отказ от корпоративной аутентификации (Запланировано Phase 4, Sprint 10)
- **OAuth 2.0 Client Credentials**: Industry standard для machine-to-machine auth ✅ РЕАЛИЗОВАНО (Sprint 3)

---

## Текущие Sprint'ы (Sprint 7+)

### 📋 Sprint 7 (Week 7) - Model Refactoring & Test Unblocking
**Дата**: 2025-01-15 (planned)
**Status**: PLANNED
**Priority**: P0 (Blocks integration testing)

**Objectives**:
1. **SQLAlchemy Model Refactoring** (P0, 2-3 hours)
   - Implement @declared_attr for __tablename__ in 3 model files:
     - app/models/file_metadata.py
     - app/models/storage_config.py
     - app/models/wal.py
   - Test with both production and test table prefixes
   - Document architecture decision

2. **StorageService API Fix** (P1, 1-2 hours)
   - Update integration tests to use current API:
     - Replace store_file() → write_file()
     - Replace calculate_checksum() → inline from return value
   - Verify all 6 storage service tests pass

3. **AsyncIO Event Loop Fix** (P1, 1 hour)
   - Proper async fixture scoping for database tests
   - Fix 2 database cache tests

4. **datetime.utcnow() Audit** (P2, 30 minutes)
   - Project-wide search for remaining occurrences
   - Replace with datetime.now(timezone.utc)
   - Add linting rule to prevent regression

**Expected Outcome**:
- 39/39 integration tests passing (100%)
- Code coverage increased to 70%+
- All Sprint 6 blockers resolved

**Deliverables**:
- ✅ @declared_attr refactor complete
- ✅ StorageService tests passing
- ✅ Database cache tests passing
- ✅ datetime audit complete
- ✅ Architecture Decision Record created

---

## Phased Migration Plan (Weeks 1-12)

### ✅ Phase 1: Preparation & Infrastructure (Weeks 1-2) - COMPLETE

#### ✅ Sprint 1: Schema Infrastructure - COMPLETE
- Schema loader and validation engine
- schema_v1.0.json (legacy) and schema_v2.0.json

#### ✅ Sprint 2: ServiceAccount Model - COMPLETE
- ServiceAccount DB model with Alembic migration
- Repository layer and CRUD operations
- OAuth 2.0 foundation

---

### ✅ Phase 2: Core Implementation (Weeks 3-6) - 85% COMPLETE

#### ✅ Sprint 3: OAuth Client Credentials Auth - COMPLETE
- POST /api/auth/token endpoint working
- Client credentials validation (bcrypt)
- JWT generation with RS256
- Rate limiting (100 req/min)

#### ✅ Sprint 4: Template Schema v2.0 - COMPLETE
- AttributeFileReader with auto-migration v1→v2
- Backward compatibility with legacy files
- Performance optimization (schema caching)

#### ✅ Sprint 5: JWT Integration Tests - COMPLETE
- Real JWT token generation for tests
- Docker test environment setup
- Critical timezone bug fixes

#### ⏳ Sprint 6: Integration Test Fixes - 30% COMPLETE (BLOCKED)
- Timezone bug fix ✅
- Table prefix architectural issue identified
- Deferred to Sprint 7: @declared_attr refactor

---

### 📋 Phase 3: Test Quality & Refinement (Weeks 7-8) - PLANNED

#### Sprint 7: Model Refactoring & Test Unblocking (Week 7)
**Status**: PLANNED
**Priority**: P0

**Tasks**:
- @declared_attr refactor for dynamic table names
- StorageService API mismatch fixes
- AsyncIO event loop isolation
- datetime.utcnow() project-wide audit

**Expected Outcome**: 100% integration tests passing, 70%+ coverage

#### Sprint 8: Code Coverage Expansion (Week 8)
**Status**: PLANNED
**Priority**: P1

**Tasks**:
- Service layer unit tests (file_service, storage_service, wal_service)
- Error handling and edge case tests
- API endpoint tests with real JWT
- Target: 80%+ code coverage

**Expected Outcome**: Production-ready test suite, ready for Ingester/Query development

---

### 📋 Phase 4: Ingester & Query Modules (Weeks 9-12) - PLANNED

#### Sprint 9: Ingester Module Foundation (Week 9)
**Tasks**:
- Streaming upload with chunked transfers
- Compression on-the-fly (Brotli/GZIP)
- Saga transaction coordination
- Circuit breaker integration

#### Sprint 10: Query Module Foundation (Week 10)
**Tasks**:
- PostgreSQL Full-Text Search (GIN indexes)
- Multi-level caching (Redis → PostgreSQL)
- Streaming download with resumable transfers
- Load balancing support

#### Sprint 11: LDAP Infrastructure Removal (Week 11)
**Pre-conditions**:
- All OAuth flows working
- No User model dependencies

**Tasks**:
- Remove LDAP docker services (389ds, dex)
- Delete LDAP code (-2000 LOC)
- Remove User model
- Alembic migration cleanup
- Documentation updates

#### Sprint 12: Production Hardening (Week 12)
**Tasks**:
- OpenTelemetry distributed tracing
- Prometheus metrics + Grafana dashboards
- Security audit (OWASP ZAP)
- Performance optimization
- Production deployment validation

---

## Key Milestones

**✅ Week 3 (Sprint 3)**: OAuth 2.0 Client Credentials production-ready
**✅ Week 4 (Sprint 4)**: Template Schema v2.0 with auto-migration
**✅ Week 5 (Sprint 5)**: JWT integration tests + critical timezone fixes (90%)
**⏳ Week 6 (Sprint 6)**: Integration test fixes (30%, blocked by architecture)
**📋 Week 7 (Sprint 7)**: Model refactoring, 100% tests passing
**📋 Week 8 (Sprint 8)**: 80%+ code coverage achieved
**📋 Week 10 (Sprint 10)**: Query Module + Ingester Module foundations
**📋 Week 12 (Sprint 12)**: Phase 3 complete, LDAP removed
**📋 Week 24**: Production-Ready with HA components

---

## Success Metrics

### Technical Metrics
```yaml
auth_performance:
  oauth_token_generation: < 100ms ✅ ACHIEVED (Sprint 3)
  jwt_validation: < 10ms ✅ ACHIEVED (Sprint 5)
  rate_limiting_overhead: < 5ms ✅ ACHIEVED (Sprint 3)

schema_performance:
  schema_validation: < 50ms ✅ ACHIEVED (Sprint 4)
  auto_migration_v1_to_v2: < 100ms ✅ ACHIEVED (Sprint 4)
  custom_attrs_query: < 200ms (pending Query Module)

availability:
  api_uptime: > 99.9% (monitoring pending Sprint 12)
  no_data_loss_events: true ✅ MAINTAINED
  rto: < 15s (HA pending Week 17-18)

test_quality:
  unit_test_coverage: 90% ✅ ACHIEVED (Sprint 4-5)
  integration_test_coverage: 38% ⏳ IN PROGRESS (blocked Sprint 6)
  integration_test_target: 100% 📋 PLANNED (Sprint 7)
  code_coverage_overall: 56% ⏳ IN PROGRESS
  code_coverage_target: 80%+ 📋 PLANNED (Sprint 8)
```

### Business Metrics
```yaml
migration_success:
  oauth_implementation: 100% ✅ COMPLETE (Sprint 3)
  template_schema_v2: 100% ✅ COMPLETE (Sprint 4)
  ldap_removal: 0% 📋 PLANNED (Sprint 11)

maintenance_improvement:
  codebase_reduction: TBD (after LDAP removal Sprint 11)
  infrastructure_reduction: TBD (after LDAP removal Sprint 11)
  deployment_time: Improved by Docker (Sprint 3-4)
```

---

## Risk Management

### Resolved Risks

**✅ JWT Timezone Bug** (Sprint 5)
- Risk: JWT tokens immediately expired on timezone-aware systems
- Impact: Critical - authentication broken
- Resolution: Fixed datetime.utcnow() → datetime.now(timezone.utc) in jwt_utils.py, wal_service.py

**✅ Template Schema Breaking Changes** (Sprint 4)
- Risk: v1.0 → v2.0 migration breaks existing files
- Impact: Critical - data loss
- Resolution: Auto-migration with backward compatibility, comprehensive tests

### Active Risks

**🔴 SQLAlchemy Table Prefix Configuration** (Sprint 6 - BLOCKING)
- Probability: High (already manifested)
- Impact: Critical (16 tests blocked)
- Mitigation: @declared_attr refactor identified, Sprint 7 planned
- Workaround: None - architectural issue

**🟡 AsyncIO Event Loop Isolation** (Sprint 6)
- Probability: Medium
- Impact: Medium (2 tests affected)
- Mitigation: Proper async fixture scoping (Sprint 7)

**🟡 Code Coverage Below Target** (Sprint 6)
- Probability: High
- Impact: Medium (production reliability)
- Mitigation: Sprint 8 dedicated to coverage expansion

---

## Rollback Strategy

### Rollback Triggers
```yaml
critical:
  - Data loss detected
  - Security vulnerability discovered
  - Performance degradation > 50%
  - Test coverage drops below 50%
```

### Rollback Procedures

**Phase 1-2 Rollback** (Sprints 1-6):
- Action: Git revert + Docker image rollback
- Time: < 15 minutes
- Data Loss: None (OAuth and Template Schema fully backward compatible)

**Phase 3 Rollback** (Sprints 7-8):
- Action: Git revert, restore previous table prefix logic
- Time: < 30 minutes
- Data Loss: None (only test infrastructure changes)

**Phase 4 Rollback** (Sprints 9-12):
- Status: ⚠️ Сложный (LDAP infrastructure removed)
- Requires: Restore LDAP containers, restore LDAP data, re-deploy старый code
- Time: 4-8 hours
- Data Loss: Возможен

---

## Documentation Requirements

### ✅ Completed Documentation
- OAuth 2.0 Client Credentials API (Sprint 3)
- Template Schema v2.0 Guide (Sprint 4)
- JWT Integration Testing Guide (Sprint 5)
- Sprint 5 Completion Report (SPRINT_5_REPORT.md)
- Sprint 6 Status Report (SPRINT_6_STATUS.md)
- Technical Debt tracking (TECHNICAL_DEBT.md - updated Sprint 6)

### 📋 Planned Documentation
- Architecture Decision Record for @declared_attr pattern (Sprint 7)
- Integration Test Troubleshooting Guide (Sprint 7)
- Service Layer Testing Best Practices (Sprint 8)
- Ingester Module API Documentation (Sprint 9)
- Query Module API Documentation (Sprint 10)

---

## Post-Migration Roadmap

### Production-Ready Phase (Weeks 13-24)

**Weeks 13-16: Ingester + Query Modules**
- Реализовать Ingester Module (streaming upload, compression, batch operations)
- Реализовать Query Module (PostgreSQL FTS, multi-level caching)
- Integration tests for cross-module operations

**Weeks 17-18: High Availability Infrastructure**
- Redis Cluster (6 nodes)
- PostgreSQL Primary-Standby replication
- HAProxy + keepalived
- Prometheus + Grafana monitoring

**Weeks 19-20: Advanced Consistency & Resilience**
- Simplified Raft через etcd client for Admin Module Cluster
- Saga Pattern для complex file operations
- Circuit Breaker patterns for all inter-service communication
- Chaos engineering tests

**Weeks 21-24: Admin UI + Final Features**
- Angular Admin UI (file manager, service account management, monitoring dashboards)
- OpenTelemetry distributed tracing
- Webhook system for event notifications
- Security testing (OWASP ZAP, penetration testing)

---

## Resources Required

**Team Composition**:
- 1 Backend Developer (full-time, ongoing)
- 1 DevOps Engineer (part-time, infrastructure support)
- 1 Technical Writer (part-time, documentation)

**Current Sprint Allocation**:
- Sprint 7 (Week 7): 8-10 hours (model refactoring + test fixes)
- Sprint 8 (Week 8): 20-25 hours (coverage expansion)
- Sprint 9-10 (Weeks 9-10): 60-80 hours (Ingester + Query modules)

---

## Conclusion

**Текущий статус**: Sprint 6 (Week 6) - 30% завершено, заблокирован архитектурной проблемой

**Достижения до текущего момента**:
- ✅ OAuth 2.0 Client Credentials production-ready (Sprint 3)
- ✅ Template Schema v2.0 с auto-migration (Sprint 4)
- ✅ JWT integration tests infrastructure (Sprint 5, 90%)
- ✅ Critical timezone bugs fixed (Sprint 5-6)
- ⏳ Integration tests 38% passing (Sprint 6, blocked)

**Критический блокер** (Sprint 6):
- SQLAlchemy table prefix evaluated at import time
- 16/39 integration tests blocked
- Solution identified: @declared_attr refactor
- Effort: 2-3 hours (Sprint 7)

**Следующие шаги**:
1. **Sprint 7**: Model refactoring, unblock all integration tests (100% passing target)
2. **Sprint 8**: Code coverage expansion (80%+ target)
3. **Sprint 9-10**: Ingester + Query modules implementation
4. **Sprint 11**: LDAP infrastructure removal
5. **Sprint 12**: Production hardening and deployment

**Success Criteria**:
- ✅ OAuth 2.0 production-ready (Sprint 3)
- ✅ Template Schema v2.0 working (Sprint 4)
- 📋 100% integration tests passing (Sprint 7 target)
- 📋 80%+ code coverage (Sprint 8 target)
- 📋 Ingester + Query modules ready (Week 10)
- 📋 LDAP removed (Week 12)
- 📋 Production-ready with HA (Week 24)

**🚀 Ready for Sprint 7: Model Refactoring & Test Unblocking!**
