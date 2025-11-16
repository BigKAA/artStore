# Alembic Migrations Backup - 2025-11-16

## Backup перед полным пересозданием миграций

**Дата**: 2025-11-16
**Причина**: Полное пересоздание Alembic миграций с учетом текущего состояния проекта

---

## Existing Migrations Summary

### Admin Module (5 migrations)
1. `20251109_2139_0df874976374_initial_schema_users_and_storage_.py`
2. `20251113_2127_add_service_accounts_table.py`
3. `20251115_1600_add_jwt_key_rotation.py`
4. `20251116_1200_add_audit_logging.py`
5. `20251116_1630_add_password_policy_fields.py`

### Storage Element (1 migration)
1. `20251114_1535_a0053fc7f95d_initial_tables_for_storage_element.py`

### Query Module (1 migration)
1. `20250115_0001_initial_schema.py`

---

## Migration Removal Plan

### Phase 1: Backup and Document
- ✅ Document all existing migrations
- ⏳ Review current database models
- ⏳ Identify critical schema features

### Phase 2: Clean Removal
- ⏳ Remove `alembic/versions/*` in all modules
- ⏳ Reset alembic_version table (if exists)
- ⏳ Keep alembic.ini and env.py

### Phase 3: Fresh Setup
- ⏳ Review and update alembic.ini configuration
- ⏳ Review and update env.py
- ⏳ Generate fresh initial migrations from current models

### Phase 4: Testing
- ⏳ Test migration generation
- ⏳ Test migration apply on clean database
- ⏳ Test migration rollback
- ⏳ Verify all tables created correctly

---

## Database Models Review

### Admin Module Models
Based on migrations, should include:
- **Users table**: User authentication and management
- **Storage elements table**: Storage element configuration
- **Service accounts table**: OAuth 2.0 service accounts
- **JWT keys table**: Key rotation management
- **Audit log table**: Security audit logging
- **Password policy fields**: Strong password enforcement

### Storage Element Models
Based on migrations, should include:
- **Storage cache table**: File metadata cache
- **Additional storage-specific tables**

### Query Module Models
Based on migrations, should include:
- **Query cache table**: Search result caching
- **File metadata cache**: Metadata from storage elements

---

## Critical Data to Preserve

### Admin Module
- Service account configurations
- JWT key rotation state
- Storage element configurations
- User accounts (if any)

### Storage Element
- File metadata cache (can be rebuilt from attr.json)

### Query Module
- Cache entries (can be rebuilt)

**Note**: Все критические данные находятся в attr.json файлах, database cache является вторичным

---

## Post-Migration Verification Checklist

### Admin Module
- [ ] Users table exists with correct schema
- [ ] Service accounts table with OAuth fields
- [ ] JWT keys table for rotation
- [ ] Audit logging table
- [ ] Password policy fields present
- [ ] All foreign keys configured
- [ ] All indexes created

### Storage Element
- [ ] Storage cache table exists
- [ ] Correct file metadata schema
- [ ] Indexes for queries

### Query Module
- [ ] Cache tables exist
- [ ] Search optimization indexes
- [ ] Metadata cache schema correct

---

## Migration Recreation Strategy

### 1. Review Current Models
Проверим все SQLAlchemy модели в каждом модуле и убедимся, что они актуальны

### 2. Single Initial Migration per Module
Создадим единую initial migration для каждого модуля, содержащую все текущие таблицы

### 3. Clean Configuration
Обновим alembic.ini и env.py для правильной работы с async engines

### 4. Testing Infrastructure
Настроим test migrations для CI/CD

---

## Notes

- Все миграции будут пересозданы с текущего состояния моделей
- Старые миграции сохранены в этом документе для справки
- Database должна быть пустой перед применением новых миграций
- Production data backup обязателен перед миграцией
