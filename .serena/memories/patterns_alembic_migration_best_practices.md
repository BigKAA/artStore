# Alembic Migration Best Practices - Learned Patterns

**Created**: 2025-11-16
**Context**: Lessons from complete migration reset and bug fixes
**Applies To**: All Python projects using Alembic + PostgreSQL

---

## Critical Pattern: Foreign Key Type Matching

### Problem
Foreign key columns MUST exactly match the type of referenced primary keys.

### Example Bug
```python
# ❌ WRONG - Type mismatch
class AuditLog:
    service_account_id = Column(Integer, ForeignKey("service_accounts.id"))

class ServiceAccount:
    id = Column(PG_UUID(as_uuid=True), primary_key=True)
```

### Solution
```python
# ✅ CORRECT - Types match
class AuditLog:
    service_account_id = Column(PG_UUID(as_uuid=True), ForeignKey("service_accounts.id"))

class ServiceAccount:
    id = Column(PG_UUID(as_uuid=True), primary_key=True)
```

### Detection
```bash
# Error message indicates type mismatch
sqlalchemy.exc.ProgrammingError: foreign key constraint cannot be implemented. 
Key columns "service_account_id" and "id" are of incompatible types: integer and uuid.
```

---

## Critical Pattern: PostgreSQL ENUM Cleanup

### Problem
PostgreSQL ENUM types persist after `DROP TABLE` and block re-creation.

### Example Bug
```python
# Migration downgrade() without ENUM cleanup
def downgrade():
    op.drop_table('service_accounts')  # Table dropped, ENUM remains!
```

### Solution
```python
# ✅ CORRECT - Explicit ENUM cleanup
def downgrade():
    op.drop_table('service_accounts')
    # Drop all ENUMs used by the table
    sa.Enum(name='service_account_role_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='service_account_status_enum').drop(op.get_bind(), checkfirst=True)
```

### Detection
```bash
# Error on re-upgrade after rollback
sqlalchemy.exc.ProgrammingError: type "service_account_role_enum" already exists
```

### Pattern Application
1. List all ENUMs: `\dT+` in psql
2. Add `sa.Enum(name='...').drop()` for each ENUM in downgrade()
3. Use `checkfirst=True` to avoid errors if ENUM doesn't exist

---

## Critical Pattern: Database Isolation for Modules

### Problem
Multiple modules sharing a database causes Alembic to detect all tables.

### Example Bug
```yaml
# ❌ WRONG - Shared database
query-module:
  database: artstore
  
storage-element:
  database: artstore  # Same database!
```

Result: Query-module migration includes storage-element tables!

### Solution
```yaml
# ✅ CORRECT - Isolated databases
query-module:
  database: artstore
  
storage-element:
  database: artstore_storage_01  # Separate database
```

### Mitigation (if shared database required)
Use `include_name` filter in `env.py`:
```python
def include_name(name, type_, parent_names):
    if type_ == "table":
        return name.startswith(f"{TABLE_PREFIX}_")
    return True

context.configure(
    include_name=include_name,
    version_table=f"{TABLE_PREFIX}_alembic_version"
)
```

---

## Critical Pattern: Alembic env.py Database URL

### Problem
Alembic env.py must set database URL from application settings.

### Example Bug
```python
# ❌ WRONG - env.py without URL configuration
config = context.config
# No URL set - uses empty value from alembic.ini!
```

### Solution
```python
# ✅ CORRECT - Set URL from application settings
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database.sync_url)
```

### Important Notes
1. Use **sync URL** (psycopg2) not async (asyncpg) for Alembic
2. Set URL BEFORE `run_migrations_online()` or `run_migrations_offline()`
3. Can override with environment variable: `SQLALCHEMY_URL=...`

---

## Pattern: Migration Testing Workflow

### Complete Test Sequence
```bash
# 1. Test upgrade
alembic upgrade head

# 2. Verify tables created
psql -c "\dt"

# 3. Test rollback
alembic downgrade base

# 4. Verify tables dropped
psql -c "\dt"

# 5. Test repeatability
alembic upgrade head

# 6. Verify tables re-created
psql -c "\dt"
```

### Automation
```python
# pytest fixture for migration testing
@pytest.fixture
def test_migration_cycle(db_engine):
    # Upgrade
    alembic.upgrade("head")
    verify_tables_exist()
    
    # Rollback
    alembic.downgrade("base")
    verify_tables_dropped()
    
    # Repeatability
    alembic.upgrade("head")
    verify_tables_exist()
```

---

## Pattern: Migration Cleanup Strategy

### When to Reset Migrations
1. **Development stage**: Frequent schema changes, no production data
2. **Critical bugs**: Type mismatches, constraint violations
3. **Architecture change**: Database restructuring, module splitting

### How to Reset Safely
```bash
# 1. Backup existing migrations
mkdir -p backups/migrations_$(date +%Y%m%d)
cp -r */alembic/versions/* backups/migrations_$(date +%Y%m%d)/

# 2. Document in claudedocs/
echo "Migration backup: $(date)" > claudedocs/MIGRATION_BACKUP_$(date +%Y%m%d).md

# 3. Drop alembic_version tables
psql -c "DROP TABLE IF EXISTS alembic_version CASCADE"

# 4. Delete migration files
rm -rf */alembic/versions/*.py

# 5. Regenerate fresh migrations
alembic revision --autogenerate -m "initial_schema"

# 6. Test thoroughly
pytest tests/test_migrations.py
```

### Never Reset If
- Production database has data
- Multiple environments depend on migration history
- Team members have applied migrations locally

---

## Pattern: Cross-Module Migration Coordination

### Problem
Module A migration depends on Module B tables existing.

### Solution: Separate Databases + Service Discovery
```yaml
# Each module has isolated database
admin-module: artstore_admin
storage-element: artstore_storage_01
query-module: artstore

# Coordination through Service Discovery (Redis)
# NOT through database foreign keys across modules
```

### Anti-Pattern
```python
# ❌ WRONG - Cross-module FK
class QueryModuleTable:
    storage_element_id = Column(Integer, ForeignKey("storage_elements.id"))
    # FK across module boundaries!
```

### Correct Pattern
```python
# ✅ CORRECT - Logical reference only
class QueryModuleTable:
    storage_element_id = Column(String(50))  # Just a string reference
    # Resolved via Service Discovery, not FK
```

---

## Pattern: Migration Message Conventions

### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Examples
```
feat(database): Add audit logging table

Creates comprehensive audit_logs table with:
- HMAC tamper protection
- Actor tracking (users, service accounts, system)
- Request correlation via OpenTelemetry

Breaking change: Requires SECURITY_AUDIT_HMAC_SECRET env var

initial_schema
```

### Semantic Versioning
- `feat`: New table/column (minor version bump)
- `fix`: Schema bug fix (patch version bump)
- `BREAKING CHANGE`: Incompatible change (major version bump)

---

## Checklist: Pre-Production Migration

```markdown
## Migration Review Checklist

### Code Quality
- [ ] All FKs match referenced PK types
- [ ] ENUMs explicitly dropped in downgrade()
- [ ] Migration message follows conventions
- [ ] No hardcoded values (use env vars)

### Testing
- [ ] Upgrade test passes
- [ ] Rollback test passes
- [ ] Repeatability test passes
- [ ] Integration tests pass

### Documentation
- [ ] Migration documented in commit message
- [ ] Breaking changes clearly marked
- [ ] Deployment steps documented
- [ ] Rollback procedure documented

### Database
- [ ] Backup procedure verified
- [ ] Restore procedure tested
- [ ] Performance impact assessed
- [ ] Index strategy reviewed

### Deployment
- [ ] Staging deployment successful
- [ ] Production backup completed
- [ ] Maintenance window scheduled
- [ ] Rollback plan prepared
```

---

## Reference: PostgreSQL ENUM Types

### Common ENUMs in ArtStore Project
```sql
-- User management
user_status_enum: ACTIVE, INACTIVE, LOCKED, DELETED
user_role_enum: ADMIN, OPERATOR, USER

-- Service accounts
service_account_status_enum: ACTIVE, SUSPENDED, EXPIRED, DELETED
service_account_role_enum: ADMIN, USER, AUDITOR, READONLY

-- Storage elements
storage_type_enum: LOCAL, S3
storage_status_enum: ONLINE, OFFLINE, DEGRADED, MAINTENANCE
storage_mode_enum: EDIT, RW, RO, AR
```

### Cleanup Template
```python
def downgrade():
    # Drop tables first
    op.drop_table('table_name')
    
    # Then drop ENUMs
    for enum_name in ['status_enum', 'role_enum', 'type_enum']:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
```

---

## Session Context

This pattern document was created during a complete Alembic migration reset that:
- Fixed 4 critical bugs
- Deleted 7 old migrations
- Created 3 new initial migrations
- Tested upgrade/rollback/repeatability for all modules

All patterns are production-tested and verified working.
