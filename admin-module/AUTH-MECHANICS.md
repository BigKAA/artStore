# Архитектурный анализ Admin Module: Аутентификация

> Документ описывает механизмы аутентификации в Admin Module системы ArtStore.
> Последнее обновление: 2025-11-26

## 1. Обзор архитектуры аутентификации

В Admin Module реализованы **две раздельные системы аутентификации**:

| Система | Назначение | Протокол |
|---------|-----------|----------|
| **Admin User** | Human-to-Machine (Admin UI) | Username/Password → JWT |
| **Service Account** | Machine-to-Machine (API) | OAuth 2.0 Client Credentials |

---

## 2. Поток аутентификации Admin User (Администратор)

### 2.1 Диаграмма потока

```
┌─────────────┐      ┌───────────────────────────┐      ┌─────────────┐
│  Admin UI   │──1──▶│ POST /api/v1/admin-auth/  │──2──▶│ PostgreSQL  │
│  (Browser)  │      │        login              │      │  AdminUser  │
└─────────────┘      └───────────────────────────┘      └─────────────┘
      │                         │                             │
      │                         │◀───────3────────────────────┘
      │                         │  (verify password, check lock)
      │◀────────4───────────────┤
      │    access_token +       │
      │    refresh_token        │
      │                         │
      │         ...             │
      │                         │
      │──5──▶ GET /api/v1/admin-auth/me (Bearer token)
      │       (Protected endpoint)
      │                         │
      │                         ├──6──▶ decode JWT, validate
      │                         │       get AdminUser from DB
      │◀────────7───────────────┤
      │    User info response   │
```

### 2.2 API Endpoints

| Endpoint | Метод | Назначение |
|----------|-------|-----------|
| `/api/v1/admin-auth/login` | POST | Вход (username/password → JWT) |
| `/api/v1/admin-auth/refresh` | POST | Обновление access token |
| `/api/v1/admin-auth/logout` | POST | Выход (client-side) |
| `/api/v1/admin-auth/me` | GET | Информация о текущем админе |
| `/api/v1/admin-auth/change-password` | POST | Смена пароля |

### 2.3 Процесс Login

**Request:**
```json
POST /api/v1/admin-auth/login
{
  "username": "admin",
  "password": "SecurePassword123"
}
```

**Внутренний процесс:**
1. Поиск AdminUser по username (case-insensitive)
2. Проверка `enabled` (аккаунт активен?)
3. Проверка `is_locked()` (не заблокирован ли после неудачных попыток?)
4. Верификация пароля через bcrypt (work factor 12)
5. При неудаче: `increment_login_attempts()` → блокировка после 5 попыток на 15 минут
6. При успехе: `reset_login_attempts()`, обновление `last_login_at`
7. Генерация JWT токенов
8. Audit logging в отдельной sync сессии

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

### 2.4 JWT Payload для Admin User

```json
{
  "sub": "admin",              // username
  "type": "admin_user",        // тип токена
  "role": "super_admin",       // роль
  "name": "admin",             // display name
  "client_id": "user_admin",   // унифицированный идентификатор
  "jti": "random-token-id",    // JWT ID для будущей revocation
  "iat": 1700000000,
  "exp": 1700001800,           // +30 минут
  "nbf": 1700000000
}
```

### 2.5 Процесс Refresh Token

**Request:**
```json
POST /api/v1/admin-auth/refresh
{
  "refresh_token": "eyJ..."
}
```

**Процесс:**
1. Декодирование refresh token
2. Проверка `type == "admin_user"`
3. Поиск AdminUser по username из payload
4. Проверка `can_login()` (enabled && !locked)
5. Генерация новой пары токенов

**Response:** Новые access_token + refresh_token

### 2.6 Защита Endpoints (Dependency)

Используется `get_current_admin_user` из `app/api/dependencies/admin_auth.py`:

1. Извлечение Bearer token из `Authorization` header
2. Декодирование JWT (RS256)
3. Проверка `type == "admin_user"`
4. Получение AdminUser из БД по username
5. Проверка `enabled` и `is_locked()`

**RBAC через RoleChecker:**
```python
@router.delete("/users/{id}")
async def delete_user(admin: AdminUser = Depends(require_super_admin)):
    ...
```

---

## 3. Поток аутентификации Service Account

### 3.1 Диаграмма потока

```
┌─────────────┐      ┌───────────────────────────┐      ┌─────────────┐
│ API Client  │──1──▶│ POST /api/v1/auth/token   │──2──▶│ PostgreSQL  │
│  (Service)  │      │ (Client Credentials)      │      │ServiceAccnt │
└─────────────┘      └───────────────────────────┘      └─────────────┘
      │                         │                             │
      │                         │◀───────3────────────────────┘
      │                         │  (verify secret, check status)
      │◀────────4───────────────┤
      │    access_token +       │
      │    refresh_token        │
      │                         │
      │──5──▶ API Request (Bearer token)
      │       (Storage/Ingester/Query)
      │                         │
      │                         ├──6──▶ validate JWT with public key
      │◀────────7───────────────┤
      │    API Response         │
```

### 3.2 API Endpoint

| Endpoint | Метод | Назначение |
|----------|-------|-----------|
| `/api/v1/auth/token` | POST | OAuth 2.0 Token (Client Credentials Grant) |

### 3.3 Процесс Token Request

**Request (RFC 6749 Section 4.4):**
```json
POST /api/v1/auth/token
{
  "client_id": "sa_prod_myapp_a1b2c3d4",
  "client_secret": "GeneratedSecretXYZ123"
}
```

**Внутренний процесс:**
1. `ServiceAccountService.authenticate_service_account()`:
   - Поиск по client_id
   - Проверка `can_authenticate()` (status=ACTIVE && !expired)
   - Верификация client_secret через bcrypt
   - Обновление `last_used_at`
2. Проверка `can_authenticate()` ещё раз на уровне endpoint
3. Создание token pair через `token_service.create_service_account_token_pair()`
4. Использование database-backed keys (если есть) или file-based fallback

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 1800,
  "issued_at": "2024-01-01T00:00:00Z"
}
```

### 3.4 JWT Payload для Service Account

```json
{
  "sub": "uuid-service-account-id",
  "type": "service_account",
  "role": "admin",
  "name": "admin-service",
  "client_id": "sa_prod_admin_service_a1b2c3d4",
  "rate_limit": 1000,
  "jti": "random-token-id",
  "iat": 1700000000,
  "exp": 1700001800,
  "nbf": 1700000000
}
```

### 3.5 Жизненный цикл Service Account

| Параметр | Значение |
|----------|----------|
| Access Token TTL | 30 минут |
| Refresh Token TTL | 7 дней |
| Secret Expiration | 90 дней |
| Rate Limit (default) | 100 req/min |

**Статусы:**
- `ACTIVE` → можно аутентифицироваться
- `SUSPENDED` → временно отключен
- `EXPIRED` → требуется ротация secret
- `DELETED` → soft delete

### 3.6 Ротация Secret

```
POST /api/v1/service-accounts/{id}/rotate-secret
```

**Процесс:**
1. Генерация нового secret через PasswordGenerator
2. Проверка password history (запрет reuse последних 5)
3. Добавление текущего хеша в `secret_history`
4. Обновление `client_secret_hash`, `secret_changed_at`, `secret_expires_at`
5. Если статус был EXPIRED → переводится в ACTIVE

---

## 4. Архитектура Token Service

### 4.1 Multi-Version Key Support

```
┌─────────────────────────────────────────────────────┐
│                  Token Validation                    │
├─────────────────────────────────────────────────────┤
│  1. Try Database Keys (if session provided)          │
│     └── JWTKey.get_active_keys() → iterate all      │
│                                                      │
│  2. Fallback to File-Based Key                       │
│     └── settings.jwt.public_key_path                │
└─────────────────────────────────────────────────────┘
```

### 4.2 Разделение методов создания токенов

| Метод | Для кого | Примечание |
|-------|----------|-----------|
| `create_token_from_data()` | Admin Users | Generic, file-based ключ |
| `create_service_account_access_token()` | Service Accounts | DB keys с fallback |
| `create_service_account_refresh_token()` | Service Accounts | DB keys с fallback |

---

## 5. Ключевые файлы

| Файл | Назначение |
|------|-----------|
| `app/api/v1/endpoints/auth.py` | OAuth 2.0 Token endpoint для Service Accounts |
| `app/api/v1/endpoints/admin_auth.py` | Login/Refresh/Logout для Admin Users |
| `app/services/token_service.py` | JWT создание и валидация (RS256) |
| `app/services/admin_auth_service.py` | Логика аутентификации Admin Users |
| `app/services/service_account_service.py` | CRUD и аутентификация Service Accounts |
| `app/api/dependencies/admin_auth.py` | FastAPI dependencies для защиты endpoints |
| `app/models/service_account.py` | SQLAlchemy модель Service Account |
| `app/models/admin_user.py` | SQLAlchemy модель Admin User |

---

## 6. Безопасность

### 6.1 Криптография

- **JWT Algorithm**: RS256 (асимметричная криптография)
- **Password Hashing**: bcrypt с work factor 12
- **Secret Generation**: cryptographically secure random (secrets module)

### 6.2 Защитные механизмы

| Механизм | Описание |
|----------|----------|
| Account Locking | Блокировка после 5 неудачных попыток на 15 минут |
| Password History | Запрет повторного использования последних 5 паролей |
| Secret Expiration | Автоматическое истечение через 90 дней |
| JWT ID (jti) | Подготовка для server-side token revocation |
| Multi-version Keys | Graceful key rotation без downtime |

### 6.3 Роли и права доступа

**Admin User Roles:**
- `SUPER_ADMIN` — полный доступ
- `ADMIN` — административные функции
- `READONLY` — только чтение

**Service Account Roles:**
- `ADMIN` — полный доступ ко всем API
- `USER` — базовые операции с файлами
- `AUDITOR` — доступ только для чтения и аудита
- `READONLY` — только чтение метаданных

---

## 7. Архитектурная диаграмма

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ADMIN MODULE                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────┐     ┌──────────────────────┐               │
│  │   admin_auth.py     │     │      auth.py         │               │
│  │   (Admin UI login)  │     │  (Service Account)   │               │
│  └──────────┬──────────┘     └──────────┬───────────┘               │
│             │                            │                           │
│             ▼                            ▼                           │
│  ┌─────────────────────┐     ┌──────────────────────┐               │
│  │ AdminAuthService    │     │ServiceAccountService │               │
│  │ - authenticate()    │     │ - authenticate_sa()  │               │
│  │ - refresh_token()   │     │ - rotate_secret()    │               │
│  │ - change_password() │     │ - verify_secret()    │               │
│  └──────────┬──────────┘     └──────────┬───────────┘               │
│             │                            │                           │
│             └──────────┬─────────────────┘                          │
│                        ▼                                             │
│             ┌─────────────────────┐                                  │
│             │   TokenService      │                                  │
│             │ - create_token_*()  │                                  │
│             │ - decode_token()    │                                  │
│             │ - validate_token()  │                                  │
│             └──────────┬──────────┘                                  │
│                        │                                             │
│          ┌─────────────┴─────────────┐                              │
│          ▼                           ▼                              │
│  ┌───────────────┐          ┌───────────────┐                       │
│  │ File-based    │          │ Database Keys │                       │
│  │ RSA Keys      │          │  (JWTKey)     │                       │
│  └───────────────┘          └───────────────┘                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Известные ограничения

| Ограничение | Описание | Рекомендация |
|-------------|----------|--------------|
| Client-side Logout | Token revocation не реализован | Добавить Redis blacklist для jti |
| Refresh Token для SA | Выдаётся, но нет endpoint для использования | Добавить `/api/v1/auth/refresh` или удалить refresh token |
| Rate Limiting | Хранится в токене, но не enforcement | Добавить middleware для проверки rate_limit |

---

## 9. Примеры использования

### 9.1 Аутентификация Admin User

```bash
# Login
curl -X POST http://localhost:8000/api/v1/admin-auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# Использование токена
curl -X GET http://localhost:8000/api/v1/admin-auth/me \
  -H "Authorization: Bearer eyJ..."

# Refresh
curl -X POST http://localhost:8000/api/v1/admin-auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

### 9.2 Аутентификация Service Account

```bash
# Получение токена
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "sa_prod_myapp_xxx", "client_secret": "secret123"}'

# Использование токена в других модулях
curl -X GET http://localhost:8010/api/v1/files \
  -H "Authorization: Bearer eyJ..."
```

---

## 10. См. также

- [README.md](../README.md) — общая документация проекта
- [DEVELOPMENT-GUIDE.md](../DEVELOPMENT-GUIDE.md) — руководство по разработке
- [admin-module/README.md](README.md) — документация Admin Module
