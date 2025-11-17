# Admin UI API Implementation Plan

**Date**: 2025-11-17
**Goal**: Реализовать недостающие API endpoints для Admin UI

---

## Current State Analysis

### ✅ Existing Endpoints

**Authentication** (`/api/auth/`):
- `POST /api/auth/token` - OAuth 2.0 Client Credentials (service accounts)
- `POST /api/auth/refresh` - Token refresh
- Поддерживает только service accounts (client_id + client_secret)

**Health Checks** (`/api/health/`):
- `GET /api/health/live` - Liveness probe
- `GET /api/health/ready` - Readiness probe

**JWT Keys** (`/api/jwt-keys/`):
- JWT key rotation management
- Public key exposure

### ✅ Existing Models

```python
# app/models/user.py - Legacy LDAP users (не используется для Admin UI)
class User(Base):
    id: UUID
    username: str
    email: str
    # LDAP integration (будет удалено в Sprint 13)

# app/models/service_account.py
class ServiceAccount(Base):
    id: UUID
    name: str
    description: str | None
    client_id: str (unique)
    client_secret_hash: str
    role: ServiceAccountRole (ADMIN, USER, READONLY)
    enabled: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None

# app/models/storage_element.py
class StorageElement(Base):
    id: UUID
    name: str
    description: str | None
    url: str
    storage_type: StorageType (local, s3)
    mode: StorageMode (edit, rw, ro, ar)
    capacity_gb: int
    retention_years: int
    # storage configuration (local_path or s3 settings)
    created_at: datetime
    updated_at: datetime
```

### ❌ Missing for Admin UI

1. **Admin Authentication** - Отдельная аутентификация для администраторов UI
2. **Service Accounts CRUD** - Full management через REST API
3. **Storage Elements CRUD** - Full management через REST API
4. **System Status** - Health и metrics всех модулей

---

## Implementation Plan

### Phase 1: Admin Authentication (Priority: P0)

**New Model**: `AdminUser`
```python
class AdminUser(Base):
    """
    Администраторы с login/password для Admin UI.
    Отдельно от service accounts (OAuth client credentials).
    """
    __tablename__ = "admin_users"

    id: UUID
    username: str (unique)
    email: str (unique)
    password_hash: str (bcrypt)
    role: AdminRole (SUPER_ADMIN, ADMIN, READ_ONLY)
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
```

**New Endpoints**:
```http
POST   /api/admin-auth/login
       Request: { "username": "admin", "password": "password" }
       Response: { "access_token": "jwt", "refresh_token": "jwt", "token_type": "Bearer", "expires_in": 1800 }

POST   /api/admin-auth/refresh
       Request: { "refresh_token": "jwt" }
       Response: { "access_token": "jwt", "expires_in": 1800 }

POST   /api/admin-auth/logout
       Authorization: Bearer <token>
       Response: { "success": true }

GET    /api/admin-auth/me
       Authorization: Bearer <token>
       Response: { "id": "uuid", "username": "admin", "email": "admin@example.com", "role": "ADMIN" }
```

**Implementation Files**:
- `app/models/admin_user.py` - SQLAlchemy model
- `app/schemas/admin_auth.py` - Pydantic schemas
- `app/services/admin_auth_service.py` - Business logic
- `app/api/v1/endpoints/admin_auth.py` - REST endpoints
- `app/api/dependencies/admin_auth.py` - JWT validation для admin users
- `alembic/versions/XXX_create_admin_users.py` - Migration

**JWT Token Differences**:
- Service Accounts JWT: `sub: client_id`, `type: service_account`
- Admin Users JWT: `sub: username`, `type: admin_user`

**Initial Admin Creation**:
```python
# app/db/init_db.py - create_initial_admin()
# Создание при первом запуске если нет admin users
username = settings.initial_admin_username or "admin"
password = settings.initial_admin_password or generate_random()
email = settings.initial_admin_email or "admin@artstore.local"
```

---

### Phase 2: Service Accounts Management (Priority: P1)

**New Endpoints**:
```http
# List with pagination, filters, search
GET    /api/service-accounts?page=1&limit=25&role=ADMIN&status=active&search=test&from=2025-01-01&to=2025-12-31
       Response: { "items": [...], "total": 243, "page": 1, "limit": 25, "pages": 10 }

# Get by ID
GET    /api/service-accounts/{id}
       Response: { "id": "uuid", "name": "...", "client_id": "...", ... }

# Create new
POST   /api/service-accounts
       Request: {
         "name": "Test Account",
         "description": "...",
         "client_id": "custom-id",
         "client_secret": "secure-secret",
         "role": "ADMIN",
         "enabled": true
       }
       Response: { "id": "uuid", "name": "...", "created_at": "..." }

# Update existing
PATCH  /api/service-accounts/{id}
       Request: { "name": "New Name", "description": "...", "role": "USER", "enabled": false }
       Response: { "id": "uuid", "name": "New Name", ... }

# Delete
DELETE /api/service-accounts/{id}
       Response: { "success": true, "deleted_at": "..." }

# Rotate secret
POST   /api/service-accounts/{id}/rotate-secret
       Response: { "client_secret": "new-generated-secret" }

# Bulk operations
POST   /api/service-accounts/bulk/delete
       Request: { "ids": ["uuid1", "uuid2"] }
       Response: { "deleted": 2, "failed": [] }

PATCH  /api/service-accounts/bulk/role
       Request: { "ids": ["uuid1"], "role": "ADMIN" }
       Response: { "updated": 1, "failed": [] }

PATCH  /api/service-accounts/bulk/status
       Request: { "ids": ["uuid1"], "enabled": false }
       Response: { "updated": 1, "failed": [] }
```

**Implementation Files**:
- `app/schemas/service_account.py` - Enhanced Pydantic schemas (add pagination)
- `app/services/service_account_service.py` - CRUD + bulk operations
- `app/api/v1/endpoints/service_accounts.py` - REST endpoints
- `app/utils/pagination.py` - Pagination helper

**Existing Model**: Already have `ServiceAccount` model ✅

**Features**:
- Pagination support (page, limit, total, pages)
- Filtering (role, status, search, date range)
- Sorting (by any field, asc/desc)
- Bulk operations (delete, role change, enable/disable)
- Secret rotation (bcrypt new password)

---

### Phase 3: Storage Elements Management (Priority: P1)

**New Endpoints**:
```http
# List with pagination, filters, search
GET    /api/storage-elements?page=1&limit=25&mode=edit,rw&type=local&search=storage1
       Response: { "items": [...], "total": 15, "page": 1, "limit": 25 }

# Get by ID with statistics
GET    /api/storage-elements/{id}
       Response: {
         "id": "uuid",
         "name": "Storage 01",
         "mode": "edit",
         "capacity_total_gb": 1000,
         "capacity_used_gb": 450,
         "file_count": 15234,
         "days_until_expiration": 1826,
         ...
       }

# Create new
POST   /api/storage-elements
       Request: {
         "name": "Storage 01",
         "url": "http://localhost:8010",
         "storage_type": "local",
         "capacity_gb": 1000,
         "retention_years": 5,
         "local": { "base_path": "/data/storage" },
         "mode": "edit"
       }
       Response: { "id": "uuid", "name": "Storage 01", ... }

# Update
PATCH  /api/storage-elements/{id}
       Request: { "name": "New Name", "capacity_gb": 2000, ... }
       Response: { "id": "uuid", "name": "New Name", ... }

# Delete
DELETE /api/storage-elements/{id}
       Response: { "success": true, "deleted_at": "..." }
       Error: { "detail": "Cannot delete storage element with files" } if files exist

# Change mode (special endpoint)
POST   /api/storage-elements/{id}/change-mode
       Request: { "new_mode": "rw" }
       Response: {
         "id": "uuid",
         "mode": "rw",
         "previous_mode": "edit",
         "changed_at": "..."
       }
```

**Implementation Files**:
- `app/schemas/storage_element.py` - Enhanced schemas (add statistics fields)
- `app/services/storage_element_service.py` - CRUD + mode change logic
- `app/api/v1/endpoints/storage_elements.py` - REST endpoints

**Existing Model**: Already have `StorageElement` model ✅

**Features**:
- Mode transition validation (edit→rw→ro→ar)
- Statistics calculation (capacity used, file count)
- Deletion protection (cannot delete if files exist)
- Connection test endpoint (optional)

---

### Phase 4: System Status Monitoring (Priority: P2)

**New Endpoint**:
```http
GET    /api/admin/system/status
       Response: {
         "modules": [
           {
             "name": "Admin Module",
             "type": "admin-module",
             "instances": [
               {
                 "id": "admin-1",
                 "url": "http://localhost:8000",
                 "status": "healthy",
                 "cpu_percent": 15.5,
                 "memory_mb": 512,
                 "disk_available_gb": 45.2,
                 "disk_total_gb": 100,
                 "active_connections": 12,
                 "rps": 150,
                 "avg_response_time_ms": 25,
                 "alerts": []
               }
             ]
           },
           {
             "name": "Storage Elements",
             "type": "storage-element",
             "instances": [ ... ]
           },
           {
             "name": "Ingester Cluster",
             "type": "ingester-module",
             "instances": [ ... ]
           },
           {
             "name": "Query Cluster",
             "type": "query-module",
             "instances": [ ... ]
           }
         ],
         "timestamp": "2025-11-17T10:30:00Z"
       }
```

**Implementation Files**:
- `app/schemas/system_status.py` - Status response schemas
- `app/services/system_monitoring_service.py` - Health check aggregation
- `app/api/v1/endpoints/system.py` - REST endpoints

**Features**:
- Aggregate health checks from all modules
- Collect metrics (CPU, memory, disk, connections, RPS)
- Detect alerts (capacity warnings, retention expiring)
- Real-time or cached (5-10 seconds cache)

**Data Sources**:
- Admin Module: Self (psutil for CPU/memory)
- Storage Elements: Health check endpoints + database queries
- Ingester/Query: Health check endpoints (via Service Discovery)

---

## Database Migrations

### Migration 1: Create admin_users table

```sql
CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_admin_users_username ON admin_users(username);
CREATE INDEX idx_admin_users_email ON admin_users(email);
CREATE INDEX idx_admin_users_enabled ON admin_users(enabled);
```

### Migration 2: Enhance service_accounts table (if needed)

```sql
-- Add last_used_at if not exists
ALTER TABLE service_accounts ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP WITH TIME ZONE;

-- Add indexes for filtering
CREATE INDEX IF NOT EXISTS idx_service_accounts_role ON service_accounts(role);
CREATE INDEX IF NOT EXISTS idx_service_accounts_enabled ON service_accounts(enabled);
CREATE INDEX IF NOT EXISTS idx_service_accounts_created_at ON service_accounts(created_at);
```

### Migration 3: Enhance storage_elements table (if needed)

```sql
-- Add indexes for filtering
CREATE INDEX IF NOT EXISTS idx_storage_elements_mode ON storage_elements(mode);
CREATE INDEX IF NOT EXISTS idx_storage_elements_storage_type ON storage_elements(storage_type);
CREATE INDEX IF NOT EXISTS idx_storage_elements_created_at ON storage_elements(created_at);
```

---

## Testing Strategy

### Unit Tests

**Admin Authentication**:
- `tests/unit/test_admin_auth_service.py` - Password hashing, token generation
- `tests/unit/test_admin_user_model.py` - Model validation

**Service Accounts**:
- `tests/unit/test_service_account_service.py` - CRUD operations, bulk operations
- `tests/unit/test_service_account_pagination.py` - Pagination logic

**Storage Elements**:
- `tests/unit/test_storage_element_service.py` - CRUD, mode transitions
- `tests/unit/test_storage_element_validation.py` - Mode transition rules

### Integration Tests

**Admin Authentication Flow**:
```python
def test_admin_login_flow():
    # Create admin user
    # Login with credentials
    # Receive JWT token
    # Use token to access protected endpoint
    # Refresh token
    # Logout
```

**Service Accounts CRUD**:
```python
def test_service_accounts_crud():
    # Create service account
    # List with pagination
    # Update service account
    # Rotate secret
    # Delete service account
```

**Bulk Operations**:
```python
def test_bulk_operations():
    # Create 10 service accounts
    # Bulk delete 5
    # Bulk change role for 3
    # Bulk disable 2
```

**Storage Elements Mode Transition**:
```python
def test_storage_mode_transitions():
    # Create storage in edit mode
    # Transition edit → rw (success)
    # Transition rw → ro (success)
    # Transition ro → ar (success)
    # Transition ar → edit (failure - not allowed via API)
```

---

## Implementation Order

### Week 1: Admin Authentication (5-8 hours)
1. ✅ Create AdminUser model
2. ✅ Create Alembic migration
3. ✅ Implement admin_auth_service (login, token generation, password hashing)
4. ✅ Create admin_auth endpoints (login, refresh, logout, me)
5. ✅ Add admin JWT validation dependency
6. ✅ Create initial admin user in init_db
7. ✅ Write unit tests
8. ✅ Write integration tests

### Week 2: Service Accounts Management (8-12 hours)
1. ✅ Enhance service_account schemas (pagination support)
2. ✅ Implement pagination utility
3. ✅ Implement service_account_service (CRUD + bulk)
4. ✅ Create service_accounts endpoints
5. ✅ Add filtering and sorting logic
6. ✅ Implement bulk operations
7. ✅ Write unit tests
8. ✅ Write integration tests

### Week 3: Storage Elements Management (8-12 hours)
1. ✅ Enhance storage_element schemas (statistics fields)
2. ✅ Implement storage_element_service (CRUD + mode change)
3. ✅ Create storage_elements endpoints
4. ✅ Add statistics calculation logic
5. ✅ Implement mode transition validation
6. ✅ Write unit tests
7. ✅ Write integration tests

### Week 4: System Status Monitoring (4-6 hours)
1. ✅ Create system_status schemas
2. ✅ Implement system_monitoring_service
3. ✅ Create system endpoints
4. ✅ Add metrics collection (psutil)
5. ✅ Write integration tests

**Total Estimated Time**: 25-38 hours (3-5 дней full-time work)

---

## Security Considerations

### Admin Authentication
- ✅ bcrypt password hashing (work factor 12)
- ✅ JWT tokens (RS256 signature)
- ✅ Refresh token rotation
- ✅ Rate limiting (max 5 login attempts per minute)
- ✅ Audit logging (all admin actions)

### Service Accounts Secret Rotation
- ✅ Generate cryptographically secure random secrets
- ✅ Minimum 32 characters
- ✅ bcrypt hashing before storage
- ✅ Audit log entry on rotation

### Authorization
- ✅ Admin JWT required for all admin endpoints
- ✅ Role-based access control (SUPER_ADMIN can manage admins)
- ✅ Service account permissions (ADMIN can manage storage elements)

### Input Validation
- ✅ Pydantic schemas for all requests
- ✅ Username/email format validation
- ✅ Password strength requirements
- ✅ Client ID uniqueness validation

---

## API Documentation

### OpenAPI (Swagger)

**Auto-generated** через FastAPI:
- `/docs` - Swagger UI
- `/redoc` - ReDoc UI
- `/openapi.json` - OpenAPI schema

**Manual Documentation**:
- Create `docs/API.md` with examples for each endpoint
- Include cURL examples
- Include response schemas
- Include error codes

---

## Deployment Considerations

### Environment Variables

```bash
# Admin Authentication
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=changeme123  # ВАЖНО: изменить в production!
INITIAL_ADMIN_EMAIL=admin@artstore.local

# JWT Configuration (shared with service accounts)
JWT_PRIVATE_KEY_PATH=/app/keys/private_key.pem
JWT_PUBLIC_KEY_PATH=/app/keys/public_key.pem
JWT_ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Rate Limiting
RATE_LIMIT_LOGIN_ATTEMPTS=5
RATE_LIMIT_WINDOW_MINUTES=1

# System Monitoring
SYSTEM_STATUS_CACHE_SECONDS=5
```

### Database Migration

```bash
# Run migration
docker-compose exec admin-module alembic upgrade head

# Rollback if needed
docker-compose exec admin-module alembic downgrade -1
```

### Docker Deployment

```yaml
# docker-compose.yml
services:
  admin-module:
    environment:
      - INITIAL_ADMIN_USERNAME=${INITIAL_ADMIN_USERNAME}
      - INITIAL_ADMIN_PASSWORD=${INITIAL_ADMIN_PASSWORD}
      - INITIAL_ADMIN_EMAIL=${INITIAL_ADMIN_EMAIL}
```

---

## Success Criteria

### Functional Requirements
- ✅ Admin can login with username/password
- ✅ Admin can manage service accounts (CRUD)
- ✅ Admin can manage storage elements (CRUD)
- ✅ Admin can view system status
- ✅ All endpoints support pagination, filtering, sorting
- ✅ Bulk operations work correctly

### Non-Functional Requirements
- ✅ API response time < 200ms (simple queries)
- ✅ API response time < 500ms (complex queries with joins)
- ✅ Pagination performance (tested with 10,000 records)
- ✅ 100% unit test coverage for critical paths
- ✅ 90%+ integration test coverage

### Security Requirements
- ✅ All passwords bcrypt hashed
- ✅ JWT tokens signed with RS256
- ✅ Rate limiting on login endpoint
- ✅ Audit logging for all admin actions
- ✅ Input validation on all endpoints

---

## Open Questions

**Q1**: Should we support multiple admin roles (SUPER_ADMIN, ADMIN, READ_ONLY) from the start or just ADMIN?
- **Recommendation**: Start with single ADMIN role, add RBAC in Phase 2

**Q2**: Rotate secret - automatic generation or manual input?
- **Recommendation**: Automatic generation (more secure), show once with warning

**Q3**: System status - real-time or cached?
- **Recommendation**: Cached (5 seconds), с опцией force refresh

**Q4**: Should we add webhooks management endpoints now or later?
- **Recommendation**: Later (Phase 3), not critical for MVP

**Q5**: Storage Element connection test - should it be part of create/update flow?
- **Recommendation**: Optional button "Test Connection", не блокирующий

---

## References

- **Specification**: `admin-ui/SPECIFICATION.md`
- **Current API**: `admin-module/app/api/v1/endpoints/`
- **Models**: `admin-module/app/models/`
- **Schemas**: `admin-module/app/schemas/`

---

**Next Action**: Start with Phase 1 - Admin Authentication implementation

