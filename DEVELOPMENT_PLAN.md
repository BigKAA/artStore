# План разработки ArtStore - С учетом архитектурных изменений

## Executive Summary

**ArtStore** - распределенная система файлового хранилища с микросервисной архитектурой для долгосрочного хранения документов.

**Статус**: В разработке - критические архитектурные изменения

**Ключевые изменения архитектуры** (2025-01-12):
1. **Упрощение аутентификации**: От LDAP к OAuth 2.0 Client Credentials (Service Accounts)
2. **Эволюция метаданных**: Template Schema для гибкой эволюции attr.json без breaking changes

**Сроки реализации**:
- **Phase 1-2 (Infrastructure + Core)**: 6 недель (текущие модули без изменений)
- **Phase 3 (Migration)**: 4 недели (координированная миграция)
- **Phase 4 (Cleanup)**: 2 недели (удаление LDAP, финализация)
- **Total Migration**: 12 недель (3 месяца)
- **Production-Ready**: 24 недели (6 месяцев с HA компонентами)

---

## Текущий статус проектаКак выглядит система (после week 2):

✅ **Завершено**:
- Admin Module: 96% (JWT Auth RS256, User CRUD, LDAP structure ready)
- Storage Element: 70% (Phase 1 complete, Phase 2 85% services)
- Infrastructure: PostgreSQL, Redis, MinIO, LDAP (389ds) deployed

⏳ **В процессе**:
- Storage Element Phase 2: Router + Docker pending
- LDAP Services: Structure ready, services implementation pending

📋 **Запланировано**:
- Ingester Module: 10% (basic structure)
- Query Module: 10% (basic structure)
- Admin UI: 0%

---

## 🔄 Критическое архитектурное изменение (2025-01-12)

### Новые требования от заказчика

**Источник**: `.archive/sq.md` + research_architecture_changes_20250112.md

**Ключевое изменение**:
> "Система не предназначена для непосредственного использования конечных пользователей.
> Системой будут пользоваться другие приложения.
> Следовательно, пользователи будут только локальные и не надо реализовывать хранение их
> учетных записей в LDAP."

**Интерпретация**:
- **Смена парадигмы**: Human users → Service Accounts (API clients)
- **Удаление LDAP**: Полный отказ от корпоративной аутентификации
- **OAuth 2.0 Client Credentials**: Industry standard для machine-to-machine auth

---

## Phased Migration Plan (12 Weeks)

### Phase 1: Preparation & Infrastructure (Weeks 1-2)

#### Sprint 1: Schema Infrastructure
**Задачи**:
- Создать `.meta/` directory structure в storage-element
- Реализовать AttrSchemaLoader service
- Создать schema_v1.0.json (legacy) и schema_v2.0.json (с custom section)
- Unit tests для schema validation

**Deliverables**:
- ✅ Schema loader работает
- ✅ Validation engine ready
- ✅ Documentation complete

**Resources**: 1 backend developer, 20 hours
**Риски**: Low

#### Sprint 2: ServiceAccount Model
**Задачи**:
- Создать ServiceAccount DB model (id, name, client_id, client_secret_hash, role, status)
- Alembic migration для service_accounts table
- Repository layer и basic CRUD operations
- Unit tests

**Deliverables**:
- ✅ service_accounts table создана
- ✅ CRUD API endpoints работают
- ✅ Unit tests pass

**Resources**: 1 backend developer, 20 hours
**Риски**: Low

---

### Phase 2: Core Implementation (Weeks 3-6)

#### Sprint 3: OAuth Client Credentials Auth
**Задачи**:
- Реализовать POST /api/auth/token endpoint
- Client credentials validation (bcrypt)
- JWT generation для service accounts
- Rate limiting middleware (100 req/min default)

**Deliverables**:
- ✅ OAuth flow работает
- ✅ Tokens генерируются correctly
- ✅ Rate limiting enforced

**Resources**: 1 backend developer, 30 hours
**Риски**: Medium (security critical)

#### Sprint 4: Attr.json v2 Reader
**Задачи**:
- Реализовать AttributeFileReader с auto-migration v1→v2
- Backward compatibility tests с legacy файлами
- Integration с Storage Element
- Performance optimization (schema caching)

**Deliverables**:
- ✅ Все legacy файлы читаются
- ✅ Migration transparent
- ✅ Performance acceptable

**Resources**: 1 backend developer, 25 hours
**Риски**: Medium (data integrity)

#### Sprint 5: Custom Attributes Writer
**Задачи**:
- Реализовать CustomAttributesManager
- Mode enforcement (edit/rw only for updates)
- Atomic write с WAL
- API endpoints (POST /api/files/{id}/custom-attributes)

**Deliverables**:
- ✅ Custom attributes API working
- ✅ Atomic updates working
- ✅ Mode checks enforced

**Resources**: 1 backend developer, 25 hours
**Риски**: Medium (concurrency)

#### Sprint 6: Dual Running Setup
**Задачи**:
- Поддержка User model + ServiceAccount model параллельно
- POST /api/auth/login (deprecated) + /api/auth/token
- Migration scripts для users → service_accounts
- Client notification templates

**Deliverables**:
- ✅ Both auth flows работают
- ✅ Migration path tested
- ✅ Documentation complete

**Resources**: 1 backend developer, 20 hours
**Риски**: High (backward compatibility)

---

### Phase 3: Migration Period (Weeks 7-10)

#### Sprint 7-8: Client Migration (4 weeks)
**Цель**: Все clients переходят на новый auth

**Activities**:
- **Week 7**: Notify all clients (email + documentation), provide migration guide, setup support channel
- **Week 8-9**: Clients migrate (self-service), monitor adoption metrics, support client issues
- **Week 10**: Verify 100% migration, prepare for cleanup

**Metrics**:
- Track old vs new auth usage
- Alert if old auth still high usage

**Deliverables**:
- ✅ 100% clients migrated to OAuth
- ✅ No /api/auth/login usage last 7 days
- ✅ Zero breaking incidents

**Resources**: Full team support
**Риски**: High (coordination с external teams)

#### Sprint 9: PostgreSQL Integration
**Задачи**:
- DB cache schema update (JSONB custom column)
- GIN indexes для custom queries
- Sync logic обновлен
- Query API для custom attrs (SELECT * WHERE custom->>'project_id' = 'PRJ-001')

**Deliverables**:
- ✅ Custom attrs queryable через PostgreSQL
- ✅ Performance tests pass
- ✅ API documentation updated

**Resources**: 1 backend developer, 25 hours
**Риски**: Medium (performance)

---

### Phase 4: Cleanup & Finalization (Weeks 11-12)

#### Sprint 10: LDAP Infrastructure Removal
**Pre-conditions**:
- ✅ All clients migrated to OAuth
- ✅ No /api/auth/login usage last 7 days
- ✅ Backup completed

**Задачи**:
- Remove LDAP docker services (389ds, dex)
- Delete LDAP code (services, background tasks)
- Remove User model (migrate data to ServiceAccount)
- Alembic migration (drop LDAP columns)
- Update configuration files

**Deliverables**:
- ✅ LDAP infrastructure gone
- ✅ Codebase clean (-2000 lines)
- ✅ Documentation updated

**Resources**: 1 backend developer, 15 hours
**Риски**: Medium (irreversible action)

#### Sprint 11: Monitoring & Documentation
**Задачи**:
- Dashboard для service account metrics
- Audit logging verification
- Schema evolution documentation
- Admin guide для custom attrs
- API documentation final review

**Deliverables**:
- ✅ Monitoring setup complete
- ✅ Documentation comprehensive
- ✅ Training materials ready

**Resources**: 1 backend developer, 15 hours
**Риски**: Low

#### Sprint 12: Production Rollout & Validation
**Задачи**:
- Production deployment
- Smoke tests
- Performance monitoring (first 48 hours)
- Incident response готовность

**Deliverables**:
- ✅ Production stable
- ✅ No critical issues
- ✅ Success metrics met

**Resources**: Full team on-call, 24 hours monitoring
**Риски**: Medium (production deployment)

---

## Success Metrics

### Technical Metrics
```yaml
auth_performance:
  oauth_token_generation: < 100ms
  jwt_validation: < 10ms
  rate_limiting_overhead: < 5ms

schema_performance:
  schema_validation: < 50ms
  auto_migration_v1_to_v2: < 100ms
  custom_attrs_query: < 200ms

availability:
  api_uptime: > 99.9%
  no_data_loss_events: true
  rto: < 15s (failover)
```

### Business Metrics
```yaml
migration_success:
  client_migration: 100% in 4 weeks
  zero_breaking_incidents: true
  support_tickets: < 10 total

maintenance_improvement:
  codebase_reduction: -2000 lines
  infrastructure_reduction: -2 containers
  deployment_time: -30%
  onboarding_complexity: -40%
```

---

## Risk Management

### Critical Risks

**1. Client Breakage during migration**
- Вероятность: High
- Impact: Critical
- Mitigation: Dual running period 2 weeks, deprecated warnings, rollback plan

**2. Data Loss при attr.json migration**
- Вероятность: Low
- Impact: Critical
- Mitigation: Backup ВСЕХ attr.json, read-only migration, rollback tested

**3. Performance Degradation от schema validation**
- Вероятность: Medium
- Impact: Medium
- Mitigation: Schema caching, async validation, performance testing

---

## Rollback Strategy

### Rollback Triggers
```yaml
critical:
  - Data loss detected
  - Multiple client failures
  - Security vulnerability discovered
  - Performance degradation > 50%
```

### Rollback Procedures

**Phase 1-2 Rollback**:
- Action: Git revert + Docker image rollback
- Time: < 15 minutes
- Data Loss: None (read-only changes)

**Phase 3 Rollback**:
- Action: Enable old auth endpoints, revert DB migration, restore from backup
- Time: < 1 hour
- Data Loss: ServiceAccounts created after migration

**Phase 4 Rollback**:
- Status: ⚠️ Сложный (LDAP infrastructure removed)
- Requires: Restore LDAP containers, restore LDAP data, re-deploy старый code
- Time: 4-8 hours
- Data Loss: Возможен

---

## Documentation Requirements

### Technical Documentation
**Создать**:
- API Migration Guide (для clients)
- OAuth Client Credentials Flow documentation
- Custom Attributes Schema Guide
- Schema Evolution Handbook
- Troubleshooting Guide

**Обновить**:
- CLAUDE.md (architecture changes)
- README.md (setup instructions)
- API OpenAPI spec
- Docker Compose setup

### Operational Documentation
**Создать**:
- Service Account Management Procedures
- Client Secret Rotation Policy
- Schema Version Management Process
- Incident Response Playbook

**Обновить**:
- Deployment Runbook
- Monitoring Dashboard Guide
- Backup & Recovery Procedures

---

## Post-Migration Roadmap

### Production-Ready Phase (Weeks 13-24)

**Weeks 13-16: Ingester + Query Modules**
- Реализовать Ingester Module (streaming upload, compression, batch operations)
- Реализовать Query Module (PostgreSQL FTS, multi-level caching)
- Integration tests

**Weeks 17-18: High Availability Infrastructure**
- Redis Cluster (6 nodes)
- PostgreSQL Primary-Standby
- HAProxy + keepalived
- Prometheus + Grafana

**Weeks 19-20: Advanced Consistency & Resilience**
- Simplified Raft через etcd client
- Saga Pattern для file operations
- Circuit Breaker patterns
- Chaos engineering tests

**Weeks 21-24: Admin UI + Final Features**
- Angular Admin UI (file manager, service account management, monitoring)
- OpenTelemetry distributed tracing
- Webhook system
- Security testing (OWASP ZAP, penetration testing)

---

## Key Milestones

**Week 2 (Completed)**: Admin Module 96%, Storage Element 70%
**Week 6**: OAuth + Template Schema implemented
**Week 10**: All clients migrated to OAuth
**Week 12**: LDAP removed, migration complete ✅
**Week 16**: Ingester + Query modules ready
**Week 24**: Production-Ready with HA

---

## Resources Required

**Team Composition**:
- 1 Backend Developer (full-time, 12 weeks)
- 1 DevOps Engineer (part-time, support infrastructure)
- 1 Technical Writer (part-time, documentation)
- Full Team on-call during migration weeks 7-10

**Budget Estimate**:
- Development: ~480 hours (1 dev × 40 hours/week × 12 weeks)
- DevOps Support: ~120 hours
- Documentation: ~80 hours
- **Total**: ~680 hours

---

## Conclusion

План сфокусирован на безопасной миграции к Service Accounts и Template Schema с минимизацией рисков:

**✅ Преимущества подхода**:
- Упрощение архитектуры (-50% auth complexity, -2000 LOC)
- Industry standard OAuth 2.0 для M2M auth
- Гибкая эволюция метаданных через Template Schema
- Zero data loss через dual running period
- Comprehensive rollback strategy

**⚠️ Критические точки контроля**:
- Week 6: Dual running period begins
- Week 8-9: Client migration monitoring
- Week 10: 100% migration verification
- Week 12: Final LDAP removal

**🎯 Success Criteria**:
- ✅ Zero breaking incidents during migration
- ✅ 100% client migration в 4 weeks
- ✅ Codebase reduction -2000 lines
- ✅ Infrastructure simplification -2 containers
- ✅ Production-ready за 24 weeks

**🚀 Готовы к старту с Week 1: Schema Infrastructure!**
