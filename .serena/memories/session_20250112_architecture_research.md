# Session 2025-01-12: Architecture Changes Research

**Дата**: 2025-01-12
**Тип**: Deep Research (standard depth)
**Статус**: ✅ Завершено

## Цель сессии

Исследование двух критических изменений архитектуры ArtStore из документа `.archive/sq.md`:
1. Упрощение модели пользователей (от LDAP к локальной аутентификации)
2. Эволюция формата `*.attr.json` (поддержка динамических атрибутов)

## Ключевые результаты

### 1. Упрощение пользователей - ✅ ОДОБРЕНО

**Рекомендация**: Service Accounts (OAuth Client Credentials)

**Обоснование:**
- Идеальное alignment с machine-to-machine use case
- Reduction: -2000 lines LDAP code, -2 Docker containers
- Industry standard approach (OAuth RFC 6749)
- Simplified maintenance (-50% auth complexity)

**Migration Strategy:**
- Dual running period: 2+ weeks
- Total duration: 12 weeks (3 months)
- Phased approach: Preparation → Implementation → Migration → Cleanup

### 2. Динамические атрибуты - ✅ ОДОБРЕН Вариант 2

**Рекомендация**: Template Schema (вместо JSON-строки)

**Архитектура:**
```
/storage/.meta/schema_vX.json  ← Template definitions
```

**Структура attr.json v2:**
```json
{
  "_meta": {"schema_version": "2.0"},
  "file": {...},     // Static core (immutable)
  "upload": {...},   // Upload metadata (immutable)
  "storage": {...},  // Storage policy (immutable after RO)
  "custom": {...}    // Dynamic custom attributes (schema-driven)
}
```

**Преимущества над Вариант 1:**
- PostgreSQL JSON queryability (GIN indexes)
- Backward compatibility (auto-migration v1→v2)
- JSON Schema validation
- Human readable format
- Long-term evolution capability

## Deliverables

**Документация:**
- ✅ [claudedocs/research_architecture_changes_20250112.md](../claudedocs/research_architecture_changes_20250112.md)
  - Полный research report (109K tokens)
  - Industry best practices analysis
  - Trade-offs comparison
  - Implementation plan (12 weeks, 4 phases, 12 sprints)
  - Risk assessment + mitigations
  - Code examples (Python)
  - Rollback procedures

## Ключевые инсайты

**Machine-to-Machine Authentication:**
- OAuth Client Credentials - стандарт для service accounts
- JWT short-lived tokens (30 min access, 7 days refresh)
- Rate limiting essential для API clients
- Mutual TLS - overkill для ArtStore use case

**JSON Schema Evolution:**
- Schema versioning в документе (semantic versioning)
- Backward compatibility rules (optional fields для additions)
- Git object format - excellent case study
- Docker manifest evolution - lessons learned

**Implementation Patterns:**
```python
# ServiceAccount model
class ServiceAccount:
    id: UUID
    name: str
    client_id: str  # Auto-generated
    client_secret_hash: str  # bcrypt
    role: Role
    rate_limit: int

# Schema loader с caching
class AttrSchemaLoader:
    async def get_schema(self, version: str) -> dict
    async def validate_attr_file(self, attr_data: dict) -> bool

# Auto-migration v1→v2
class AttributeFileReader:
    async def migrate_v1_to_v2(self, v1_data: dict) -> dict
```

## Риски и митигации

**Critical Risks:**
1. **Client breakage** (High) → Dual running 2 weeks + deprecated warnings
2. **Data loss** (Low) → Full backup + read-only migrations
3. **Performance degradation** (Medium) → Schema caching + async validation

**Risk Matrix:**
- LDAP Removal: Medium complexity, Medium risk, 2 weeks
- ServiceAccount Model: Low complexity, Low risk, 1 week
- Auth Endpoint Migration: Medium complexity, High risk, 2 weeks
- Schema Loader: Medium complexity, Low risk, 1 week
- Custom Attrs API: Medium complexity, Medium risk, 2 weeks

## Success Metrics

**Technical:**
- OAuth token generation: < 100ms
- Schema validation: < 50ms
- API uptime: > 99.9%

**Business:**
- Client migration: 100% in 4 weeks
- Codebase reduction: -2000 lines
- Infrastructure reduction: -2 containers
- Deployment time: -30%

## Рекомендации для следующих шагов

**Immediate Actions:**
1. ✅ Review research report с командой
2. ⏳ Discuss с заказчиком timeline и priorities
3. ⏳ Prepare client coordination plan (1 month advance notice)
4. ⏳ Setup staging environment для testing

**Before Implementation:**
- [ ] Client notification process готов
- [ ] Rollback procedures tested
- [ ] Team capacity confirmed (1 backend dev × 12 weeks)
- [ ] Documentation templates ready

**Implementation Order:**
1. Storage Element Phase 2 (current priority) ← СНАЧАЛА ЗАВЕРШИТЬ
2. Architecture changes implementation (после Phase 2)

## Research Sources

**Web Search Results:**
- Service-to-service authentication best practices (2024)
- JSON schema evolution patterns
- Docker image metadata versioning
- Dynamic attributes database design
- OAuth 2.0 Client Credentials standards

**Project Memory References:**
- project_overview
- tech_stack
- ldap_integration_specification (detailed 8-phase plan exists)

## Next Session Recommendations

**Priority 1: Storage Element Phase 2**
- Continue implementation work
- Architecture changes research complete (этот session)

**Priority 2: Architecture Changes (Future)**
- После завершения Storage Element Phase 2
- Start с Phase 1: Preparation (schema infrastructure)

**Context для продолжения:**
- Research report location: `claudedocs/research_architecture_changes_20250112.md`
- Decision: ✅ APPROVE оба изменения (Service Accounts + Template Schema)
- Timeline: 12 weeks total implementation
- Current focus: Завершить Storage Element Phase 2 first
