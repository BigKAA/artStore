# JWT Authentication и RBAC для Storage Element

Полная документация по системе аутентификации и авторизации.

## Обзор

Storage Element использует:
- **JWT tokens с RS256** для distributed authentication
- **RBAC (Role-Based Access Control)** для fine-grained permissions
- **Bearer token** для всех protected API endpoints

## Архитектура

```
Admin Module Cluster → Генерация JWT токенов (RS256)
                     → Private key хранится в Admin Module
                     ↓
Storage Element      → Публичный ключ для валидации
                     → Autonomous validation без Admin Module
```

### Преимущества
- **Distributed validation**: Storage Element валидирует токены независимо
- **No central dependencies**: Admin Module может быть недоступен
- **High performance**: Валидация через публичный ключ быстрая
- **Secure**: RS256 asymmetric encryption

## Роли Пользователей

### ADMIN
- **Полный доступ** ко всем операциям системы
- Управление пользователями и storage elements
- Системное администрирование

**Permissions**:
- Все file operations (create, read, update, delete)
- Все metadata operations
- Mode transitions
- Administrative operations (users, storage, system)

### OPERATOR
- **Управление storage** и режимами работы
- Чтение файлов и метаданных
- Переключение storage modes

**Permissions**:
- File read и search
- Metadata read
- Mode transitions
- Storage administration

**Use Case**: Операторы ЦОД управляющие режимами хранения

### USER
- **Стандартный пользователь** с основными файловыми операциями
- Создание, чтение, обновление, удаление своих файлов
- Управление метаданными

**Permissions**:
- File operations (create, read, update, delete)
- Metadata operations
- Mode info reading

**Use Case**: Обычные пользователи работающие с файлами

### READONLY
- **Только чтение** файлов и метаданных
- Поиск файлов

**Permissions**:
- File read и search
- Metadata read
- Mode info reading

**Use Case**: Аудиторы, external integrations с read-only доступом

## Матрица Разрешений

| Permission | ADMIN | OPERATOR | USER | READONLY |
|-----------|-------|----------|------|----------|
| `file:create` | ✅ | ❌ | ✅ | ❌ |
| `file:read` | ✅ | ✅ | ✅ | ✅ |
| `file:update` | ✅ | ❌ | ✅ | ❌ |
| `file:delete` | ✅ | ❌ | ✅ | ❌ |
| `file:search` | ✅ | ✅ | ✅ | ✅ |
| `metadata:read` | ✅ | ✅ | ✅ | ✅ |
| `metadata:update` | ✅ | ❌ | ✅ | ❌ |
| `mode:read` | ✅ | ✅ | ✅ | ✅ |
| `mode:transition` | ✅ | ✅ | ❌ | ❌ |
| `admin:users` | ✅ | ❌ | ❌ | ❌ |
| `admin:storage` | ✅ | ✅ | ❌ | ❌ |
| `admin:system` | ✅ | ❌ | ❌ | ❌ |

## JWT Token Format

### Token Payload

```json
{
  "sub": "user_id_123",
  "username": "ivanov",
  "roles": ["user", "operator"],
  "email": "ivanov@example.com",
  "full_name": "Ivan Ivanov",
  "exp": 1735777200,
  "iat": 1735775400
}
```

### Required Fields
- `sub` - User ID (subject)
- `username` - Username
- `roles` - Array of role strings
- `exp` - Expiration timestamp (UTC)
- `iat` - Issued at timestamp (UTC)

### Optional Fields
- `email` - User email
- `full_name` - User full name

### Token Lifetime
- **Access Token**: 30 minutes
- **Refresh Token**: 7 days

## API Usage

### Authentication Header

Все protected endpoints требуют `Authorization` header:

```http
GET /api/v1/mode/info HTTP/1.1
Host: storage-element.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Error Responses

#### 401 Unauthorized - Missing Token
```json
{
  "detail": "Missing authorization token"
}
```

#### 401 Unauthorized - Invalid Token
```json
{
  "detail": "Invalid token: Signature has expired"
}
```

#### 403 Forbidden - Insufficient Permissions
```json
{
  "detail": "User ivanov does not have permission: mode:transition"
}
```

## Примеры Использования

### Mode API Endpoints

#### GET /api/v1/mode/info
**Required Permission**: `mode:read`
**Required Roles**: Any authenticated user

```bash
curl -X GET "http://localhost:8010/api/v1/mode/info" \
  -H "Authorization: Bearer $TOKEN"
```

**Response**:
```json
{
  "current_mode": "rw",
  "allowed_operations": ["create", "read", "update"],
  "possible_transitions": ["ro"],
  "can_delete": false,
  "can_create": true,
  "can_update": true,
  "read_only": false,
  "is_archived": false
}
```

#### POST /api/v1/mode/transition
**Required Roles**: `ADMIN` или `OPERATOR`

```bash
curl -X POST "http://localhost:8010/api/v1/mode/transition" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_mode": "ro",
    "reason": "Storage approaching capacity"
  }'
```

**Success Response** (200):
```json
{
  "success": true,
  "from_mode": "rw",
  "to_mode": "ro",
  "message": "Successfully transitioned to ro mode",
  "current_mode_info": { ... }
}
```

**Authorization Failure** (403):
```json
{
  "detail": "Administrator or operator role required"
}
```

## Development Setup

### 1. Генерация Test RSA Keys

Для локальной разработки:

```bash
cd storage-element
mkdir -p keys

# Generate private key
openssl genrsa -out keys/private_key.pem 2048

# Generate public key
openssl rsa -in keys/private_key.pem -pubout -out keys/public_key.pem
```

**IMPORTANT**: В production используйте keys из Admin Module Cluster!

### 2. Конфигурация

`config.yaml`:
```yaml
auth:
  jwt_public_key_path: "./keys/public_key.pem"
  jwt_algorithm: "RS256"
```

Environment variables:
```bash
export AUTH__JWT_PUBLIC_KEY_PATH="./keys/public_key.pem"
export AUTH__JWT_ALGORITHM="RS256"
```

### 3. Создание Test Tokens

Используя private key для тестирования:

```python
import jwt
from datetime import datetime, timedelta, timezone

private_key = open('keys/private_key.pem').read()

payload = {
    "sub": "test_user_123",
    "username": "testuser",
    "roles": ["user"],
    "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
    "iat": int(datetime.now(timezone.utc).timestamp())
}

token = jwt.encode(payload, private_key, algorithm="RS256")
print(token)
```

## FastAPI Dependencies

### Базовые Dependencies

```python
from fastapi import Depends
from app.api.dependencies import get_current_user
from app.core.auth import User

@app.get("/protected")
async def protected_endpoint(current_user: User = Depends(get_current_user)):
    return {"user": current_user.username}
```

### Permission Checks

```python
from app.api.dependencies import require_permission
from app.core.auth import Permission

@app.post(
    "/files",
    dependencies=[Depends(require_permission(Permission.FILE_CREATE))]
)
async def create_file():
    ...
```

### Multiple Permissions (Any)

```python
from app.api.dependencies import require_any_permission

@app.post(
    "/files",
    dependencies=[Depends(require_any_permission([
        Permission.FILE_CREATE,
        Permission.ADMIN_STORAGE
    ]))]
)
async def create_file():
    ...
```

### Role Checks

```python
from app.api.dependencies import require_role, require_operator_or_admin
from app.core.auth import UserRole

# Single role
@app.post(
    "/admin/system",
    dependencies=[Depends(require_role(UserRole.ADMIN))]
)
async def system_operation():
    ...

# Multiple roles (convenience)
@app.post(
    "/storage/manage",
    dependencies=[Depends(require_operator_or_admin)]
)
async def manage_storage():
    ...
```

### Manual Permission Checks

```python
from app.core.auth import check_permission, Permission, AuthorizationError
from fastapi import HTTPException

@app.post("/complex-operation")
async def complex_operation(current_user: User = Depends(get_current_user)):
    # Manual permission check
    try:
        check_permission(current_user, Permission.FILE_DELETE)
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Business logic
    ...
```

## Security Best Practices

### 1. Public Key Management
- ✅ Публичный ключ должен быть read-only для application
- ✅ Используйте secure storage для ключей в production
- ✅ Регулярно обновляйте ключи (automatic rotation в Admin Module)
- ❌ Никогда не храните private key в Storage Element

### 2. Token Validation
- ✅ Всегда проверяйте signature verification
- ✅ Проверяйте expiration время
- ✅ Validate required claims (sub, username, roles)
- ✅ Log всех failed authentication attempts

### 3. Permission Enforcement
- ✅ Используйте FastAPI dependencies для automatic checks
- ✅ Apply principle of least privilege
- ✅ Audit log для privileged operations
- ❌ Не доверяйте client-side role checks

### 4. Error Handling
- ✅ Generic error messages для security (не раскрывайте system details)
- ✅ Детальное logging для debugging
- ✅ Rate limiting для защиты от brute force
- ✅ Monitor suspicious authentication patterns

## Testing

### Unit Tests

```bash
pytest tests/test_auth.py -v
```

**Coverage**:
- User model и permission checks (7 tests)
- Role permission matrix (4 tests)
- JWT validator (7 tests)
- Permission check functions (6 tests)
- Integration scenarios (3 tests)

**Total: 27 tests**

### Integration Tests

Тестирование с real JWT tokens:

```python
def test_protected_endpoint_with_valid_token(test_client, valid_token):
    response = test_client.get(
        "/api/v1/mode/info",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 200

def test_protected_endpoint_without_token(test_client):
    response = test_client.get("/api/v1/mode/info")
    assert response.status_code == 401

def test_insufficient_permissions(test_client, readonly_user_token):
    response = test_client.post(
        "/api/v1/mode/transition",
        headers={"Authorization": f"Bearer {readonly_user_token}"},
        json={"target_mode": "ro"}
    )
    assert response.status_code == 403
```

## Troubleshooting

### Public Key Not Found

```
FileNotFoundError: JWT public key not found: ./keys/public_key.pem
```

**Solution**:
1. Проверьте путь к публичному ключу в config.yaml
2. Убедитесь что файл существует и readable
3. В production получите ключ из Admin Module

### Token Validation Failed

```
AuthenticationError: Invalid token: Signature has expired
```

**Solutions**:
- Проверьте что token не expired (exp claim)
- Refresh token через Admin Module
- Проверьте system clock sync (NTP)

### Permission Denied

```
HTTPException 403: User does not have permission: mode:transition
```

**Solutions**:
- Проверьте роли пользователя в токене
- Убедитесь что роль имеет требуемое разрешение
- Обратитесь к Admin Module для изменения ролей

## Production Deployment

### 1. Key Distribution

```bash
# На Admin Module Cluster
./scripts/distribute-public-key.sh storage-element-01

# Storage Element автоматически загружает ключ
```

### 2. Automatic Key Rotation

Admin Module автоматически ротирует ключи каждые 24 часа:
- Генерация новой key pair
- Distribution публичного ключа на все Storage Elements
- Graceful transition period (старые токены валидны еще 1 час)

### 3. Monitoring

Мониторинг authentication metrics:
```yaml
metrics:
  - jwt_validation_total (counter)
  - jwt_validation_failures (counter)
  - jwt_validation_duration_seconds (histogram)
  - permission_denied_total (counter by permission)
```

### 4. Logging

Все authentication события логируются:
```json
{
  "event": "jwt_validation_failed",
  "error": "Token expired",
  "timestamp": "2025-01-08T20:00:00Z",
  "user_agent": "Mozilla/5.0..."
}
```

## Миграция с Basic Auth

Если используете Basic Authentication, migration plan:

1. **Phase 1**: Dual mode (Basic + JWT)
2. **Phase 2**: Deprecate Basic Auth warnings
3. **Phase 3**: JWT only mode

См. `docs/MIGRATION_TO_JWT.md` для деталей.

## FAQ

**Q: Можно ли использовать HS256 вместо RS256?**
A: Нет, HS256 требует shared secret между всеми сервисами. RS256 позволяет distributed validation.

**Q: Как обновить роли пользователя?**
A: Роли управляются через Admin Module. После изменения требуется refresh токена.

**Q: Что если Admin Module недоступен?**
A: Storage Element продолжает работать - валидация через публичный ключ автономна.

**Q: Можно ли отозвать конкретный токен?**
A: Currently нет. Используйте short expiration (30 min) и refresh tokens.

## Ссылки

- [JWT RFC 7519](https://tools.ietf.org/html/rfc7519)
- [RS256 Algorithm](https://tools.ietf.org/html/rfc7518#section-3.3)
- [RBAC Best Practices](https://en.wikipedia.org/wiki/Role-based_access_control)
- Admin Module API Documentation
- Storage Element API Documentation
