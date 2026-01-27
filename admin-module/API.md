# Admin Module - API Reference

> Версия API: v1
> Base URL: `http://{host}:8000/api/v1`

---

## Содержание

- [Аутентификация](#аутентификация)
  - [Типы аутентификации](#типы-аутентификации)
- [OAuth 2.0 API (Service Accounts)](#oauth-20-api-service-accounts)
  - [POST /auth/token](#post-authtoken)
- [Admin Auth API (Admin UI)](#admin-auth-api-admin-ui)
  - [POST /admin-auth/login](#post-admin-authlogin)
  - [POST /admin-auth/refresh](#post-admin-authrefresh)
  - [POST /admin-auth/logout](#post-admin-authlogout)
  - [GET /admin-auth/me](#get-admin-authme)
  - [POST /admin-auth/change-password](#post-admin-authchange-password)
- [Admin Users API](#admin-users-api)
  - [POST /admin-users/](#post-admin-users)
  - [GET /admin-users/](#get-admin-users)
  - [GET /admin-users/{admin_id}](#get-admin-usersadmin_id)
  - [PUT /admin-users/{admin_id}](#put-admin-usersadmin_id)
  - [DELETE /admin-users/{admin_id}](#delete-admin-usersadmin_id)
  - [POST /admin-users/{admin_id}/reset-password](#post-admin-usersadmin_idreset-password)
- [Service Accounts API](#service-accounts-api)
  - [POST /service-accounts/](#post-service-accounts)
  - [GET /service-accounts/](#get-service-accounts)
  - [GET /service-accounts/{id}](#get-service-accountsid)
  - [PUT /service-accounts/{id}](#put-service-accountsid)
  - [DELETE /service-accounts/{id}](#delete-service-accountsid)
  - [POST /service-accounts/{id}/rotate-secret](#post-service-accountsidrotate-secret)
- [Storage Elements API](#storage-elements-api)
  - [POST /storage-elements/discover](#post-storage-elementsdiscover)
  - [POST /storage-elements/](#post-storage-elements)
  - [GET /storage-elements/](#get-storage-elements)
  - [GET /storage-elements/{id}](#get-storage-elementsid)
  - [PUT /storage-elements/{id}](#put-storage-elementsid)
  - [DELETE /storage-elements/{id}](#delete-storage-elementsid)
  - [POST /storage-elements/sync/{id}](#post-storage-elementssyncid)
  - [POST /storage-elements/sync-all](#post-storage-elementssync-all)
  - [GET /storage-elements/stats/summary](#get-storage-elementsstatssummary)
- [JWT Keys API](#jwt-keys-api)
  - [GET /jwt-keys/status](#get-jwt-keysstatus)
  - [GET /jwt-keys/active](#get-jwt-keysactive)
  - [POST /jwt-keys/rotate](#post-jwt-keysrotate)
  - [GET /jwt-keys/history](#get-jwt-keyshistory)
- [Files API (Internal)](#files-api-internal)
  - [POST /files](#post-files)
  - [GET /files/{file_id}](#get-filesfile_id)
  - [PUT /files/{file_id}](#put-filesfile_id)
  - [DELETE /files/{file_id}](#delete-filesfile_id)
  - [GET /files](#get-files)
- [Internal API](#internal-api)
  - [GET /internal/storage-elements/available](#get-internalstorage-elementsavailable)
  - [GET /internal/storage-elements/{element_id}](#get-internalstorage-elementselement_id)
- [Health API](#health-api)
  - [GET /health/live](#get-healthlive)
  - [GET /health/ready](#get-healthready)
  - [GET /health/startup](#get-healthstartup)
  - [GET /health/metrics](#get-healthmetrics)
- [Модели данных](#модели-данных)
- [Коды ошибок](#коды-ошибок)

---

## Аутентификация

### Типы аутентификации

| Тип | Назначение | Endpoint |
|-----|-----------|----------|
| **Service Account (M2M)** | Machine-to-machine: Ingester, Query, Storage | `POST /api/v1/auth/token` |
| **Admin User (H2M)** | Human-to-machine: Admin UI | `POST /api/v1/admin-auth/login` |

Все endpoints (кроме `/health/*` и token endpoints) требуют JWT Bearer token:

```http
Authorization: Bearer <jwt_token>
```

---

## OAuth 2.0 API (Service Accounts)

### POST /auth/token

OAuth 2.0 Client Credentials Grant (RFC 6749) для Service Accounts.

**Content-Type:** `application/json`

#### Тело запроса

| Поле | Тип | Описание |
|------|-----|----------|
| `client_id` | string | Client ID Service Account |
| `client_secret` | string | Client Secret Service Account |

#### Пример запроса

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "sa_prod_ingester_abc123",
    "client_secret": "your-secret-here"
  }'
```

#### Ответ 200 OK

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 1800,
  "issued_at": "2025-01-27T14:30:45Z"
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 401 | Неверный client_id или client_secret |
| 403 | Service Account заблокирован или secret истек |

---

## Admin Auth API (Admin UI)

### POST /admin-auth/login

Аутентификация администратора по username/password.

#### Тело запроса

| Поле | Тип | Описание |
|------|-----|----------|
| `username` | string | Username администратора |
| `password` | string | Пароль |

#### Пример запроса

```bash
curl -X POST http://localhost:8000/api/v1/admin-auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123"
  }'
```

#### Ответ 200 OK

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 401 | Неверный username или password |
| 403 | Аккаунт отключен |
| 423 | Аккаунт заблокирован (превышен лимит попыток) |

---

### POST /admin-auth/refresh

Обновление access token через refresh token.

#### Тело запроса

```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIs..."
}
```

#### Ответ 200 OK

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

---

### POST /admin-auth/logout

Выход администратора из системы.

**Требует:** JWT Bearer token

#### Ответ 200 OK

```json
{
  "success": true,
  "message": "Successfully logged out"
}
```

---

### GET /admin-auth/me

Получение информации о текущем администраторе.

**Требует:** JWT Bearer token

#### Ответ 200 OK

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "admin",
  "email": "admin@artstore.local",
  "role": "super_admin",
  "enabled": true,
  "last_login_at": "2025-01-27T14:30:45Z",
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

### POST /admin-auth/change-password

Смена пароля текущего администратора.

**Требует:** JWT Bearer token

#### Тело запроса

```json
{
  "current_password": "OldPassword123",
  "new_password": "NewSecurePassword456",
  "confirm_password": "NewSecurePassword456"
}
```

#### Ответ 200 OK

```json
{
  "success": true,
  "message": "Password changed successfully",
  "password_changed_at": "2025-01-27T14:30:45Z"
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 400 | Пароли не совпадают или пароль в истории |
| 401 | Неверный текущий пароль |

---

## Admin Users API

Управление администраторами системы.

### POST /admin-users/

Создание нового администратора.

**Требует:** SUPER_ADMIN роль

#### Тело запроса

```json
{
  "username": "john_doe",
  "email": "john.doe@artstore.local",
  "password": "SecurePassword123",
  "role": "admin",
  "enabled": true
}
```

#### Валидация

- `username`: 3-100 символов, латиница + цифры + дефис + underscore
- `email`: валидный email, уникальный
- `password`: минимум 8 символов, заглавная буква, строчная буква, цифра
- `role`: `super_admin` | `admin` | `readonly`

#### Ответ 201 Created

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "john_doe",
  "email": "john.doe@artstore.local",
  "role": "admin",
  "enabled": true,
  "created_at": "2025-01-27T14:30:45Z"
}
```

---

### GET /admin-users/

Получение списка администраторов с пагинацией.

**Требует:** JWT Bearer token (любая роль)

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `page` | int | Номер страницы (default: 1) |
| `page_size` | int | Размер страницы (default: 10, max: 100) |
| `role` | string | Фильтр по роли |
| `enabled` | bool | Фильтр по статусу |
| `search` | string | Поиск по username или email |

#### Ответ 200 OK

```json
{
  "items": [...],
  "total": 50,
  "page": 1,
  "page_size": 10,
  "pages": 5
}
```

---

### GET /admin-users/{admin_id}

Получение администратора по ID.

**Требует:** JWT Bearer token (любая роль)

---

### PUT /admin-users/{admin_id}

Обновление администратора.

**Требует:** SUPER_ADMIN роль

#### Тело запроса

```json
{
  "email": "new.email@artstore.local",
  "role": "readonly",
  "enabled": false
}
```

> **Ограничение:** Системный администратор (is_system=true) не может быть изменен.

---

### DELETE /admin-users/{admin_id}

Удаление администратора.

**Требует:** SUPER_ADMIN роль

> **Ограничение:** Системный администратор не может быть удален.

---

### POST /admin-users/{admin_id}/reset-password

Сброс пароля администратора.

**Требует:** SUPER_ADMIN роль

#### Тело запроса

```json
{
  "new_password": "NewSecurePassword123"
}
```

---

## Service Accounts API

Управление Service Accounts для M2M аутентификации.

### POST /service-accounts/

Создание нового Service Account.

**Требует:** SUPER_ADMIN роль

#### Тело запроса

```json
{
  "name": "ingester-service",
  "description": "Ingester Module Service Account",
  "role": "ADMIN",
  "rate_limit": 1000,
  "environment": "prod",
  "is_system": false
}
```

#### Ответ 201 Created

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "ingester-service",
  "client_id": "sa_prod_ingester_abc123",
  "client_secret": "generated-secret-shown-only-once",
  "role": "ADMIN",
  "status": "ACTIVE",
  "rate_limit": 1000,
  "secret_expires_at": "2025-04-27T14:30:45Z",
  "created_at": "2025-01-27T14:30:45Z"
}
```

> **ВАЖНО:** `client_secret` отображается ТОЛЬКО при создании!

---

### GET /service-accounts/

Получение списка Service Accounts.

**Требует:** JWT Bearer token (любая роль)

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `skip` | int | Offset пагинации (default: 0) |
| `limit` | int | Лимит записей (default: 100, max: 1000) |
| `role` | string | Фильтр по роли (ADMIN, USER, AUDITOR, READONLY) |
| `status` | string | Фильтр по статусу (ACTIVE, SUSPENDED, EXPIRED, DELETED) |
| `search` | string | Поиск по name или client_id |

---

### GET /service-accounts/{id}

Получение Service Account по ID (без client_secret).

---

### PUT /service-accounts/{id}

Обновление Service Account.

**Требует:** SUPER_ADMIN роль

#### Тело запроса

```json
{
  "name": "new-name",
  "description": "New description",
  "role": "USER",
  "rate_limit": 500,
  "status": "SUSPENDED"
}
```

> **Ограничение:** Системные Service Accounts (is_system=true) не могут быть изменены.

---

### DELETE /service-accounts/{id}

Удаление Service Account (soft delete).

**Требует:** SUPER_ADMIN роль

---

### POST /service-accounts/{id}/rotate-secret

Ротация client_secret Service Account.

**Требует:** SUPER_ADMIN роль

#### Ответ 200 OK

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "ingester-service",
  "client_id": "sa_prod_ingester_abc123",
  "new_client_secret": "new-secret-shown-only-once",
  "secret_expires_at": "2025-04-27T14:30:45Z",
  "status": "ACTIVE"
}
```

> **ВАЖНО:** `new_client_secret` отображается ТОЛЬКО при ротации!

---

## Storage Elements API

Управление Storage Elements с auto-discovery.

### POST /storage-elements/discover

Discovery Storage Element по URL без регистрации (preview).

**Требует:** JWT Bearer token (любая роль)

#### Тело запроса

```json
{
  "api_url": "http://se-01:8010"
}
```

#### Ответ 200 OK

```json
{
  "name": "se-01",
  "display_name": "Storage Element 01",
  "version": "0.1.0",
  "mode": "edit",
  "storage_type": "local",
  "base_path": "/data/storage",
  "capacity_bytes": 10737418240,
  "used_bytes": 5368709120,
  "file_count": 150,
  "status": "online",
  "api_url": "http://se-01:8010",
  "capacity_gb": 10.0,
  "used_gb": 5.0,
  "usage_percent": 50.0,
  "already_registered": false,
  "existing_id": null
}
```

---

### POST /storage-elements/

Создание Storage Element с auto-discovery.

**Требует:** SUPER_ADMIN роль

#### Тело запроса

```json
{
  "api_url": "http://se-01:8010",
  "name": "Primary Edit Storage",
  "description": "Main storage for temporary files",
  "api_key": "optional-api-key",
  "retention_days": 30,
  "is_replicated": false,
  "replica_count": 0
}
```

> **Auto-discovered fields:** mode, storage_type, base_path, capacity_bytes, used_bytes, file_count

---

### GET /storage-elements/

Получение списка Storage Elements.

**Требует:** JWT Bearer token (любая роль)

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `skip` | int | Offset пагинации |
| `limit` | int | Лимит записей |
| `mode` | string | Фильтр по режиму (edit, rw, ro, ar) |
| `status` | string | Фильтр по статусу (online, offline, degraded, maintenance) |
| `storage_type` | string | Фильтр по типу (local, s3) |
| `search` | string | Поиск по name или api_url |

---

### GET /storage-elements/{id}

Получение Storage Element по ID с вычисленными метриками.

---

### PUT /storage-elements/{id}

Обновление Storage Element.

**Требует:** SUPER_ADMIN роль

> **ВАЖНО:** Mode НЕ может быть изменен через API - только через конфигурацию SE и перезапуск.

#### Обновляемые поля

- `name`, `description`, `api_url`, `api_key`
- `status` (online/offline/degraded/maintenance)
- `retention_days`, `replica_count`

---

### DELETE /storage-elements/{id}

Удаление Storage Element.

**Требует:** SUPER_ADMIN роль

> **Ограничение:** Нельзя удалить SE с файлами (file_count > 0).

---

### POST /storage-elements/sync/{id}

Ручная синхронизация данных Storage Element.

**Требует:** JWT Bearer token (любая роль)

#### Ответ 200 OK

```json
{
  "storage_element_id": 1,
  "name": "se-01",
  "success": true,
  "changes": [
    "used_bytes: 5368709120 → 5905580032",
    "file_count: 150 → 165"
  ],
  "error_message": null,
  "synced_at": "2025-01-27T14:30:45Z"
}
```

---

### POST /storage-elements/sync-all

Массовая синхронизация всех Storage Elements.

**Требует:** SUPER_ADMIN роль

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `only_online` | bool | Синхронизировать только ONLINE (default: true) |

---

### GET /storage-elements/stats/summary

Сводная статистика по всем Storage Elements.

**Требует:** JWT Bearer token (любая роль)

#### Ответ 200 OK

```json
{
  "total_count": 3,
  "by_status": {"online": 2, "offline": 1},
  "by_mode": {"edit": 1, "rw": 2},
  "by_type": {"local": 2, "s3": 1},
  "total_capacity_gb": 30.0,
  "total_used_gb": 15.5,
  "total_files": 450,
  "average_usage_percent": 51.67
}
```

---

## JWT Keys API

Мониторинг и управление JWT key rotation.

### GET /jwt-keys/status

Получение статуса JWT key rotation.

**Требует:** ADMIN роль

#### Ответ 200 OK

```json
{
  "rotation_enabled": true,
  "rotation_interval_hours": 24,
  "active_keys_count": 2,
  "latest_key": {
    "version": "550e8400-e29b-41d4-a716-446655440000",
    "algorithm": "RS256",
    "created_at": "2025-01-27T00:00:00Z",
    "expires_at": "2025-01-28T01:00:00Z",
    "is_active": true
  },
  "next_rotation_at": "2025-01-28T00:00:00Z",
  "last_rotation_at": "2025-01-27T00:00:00Z",
  "rotation_in_progress": false
}
```

---

### GET /jwt-keys/active

Получение списка активных JWT ключей.

**Требует:** ADMIN роль

---

### POST /jwt-keys/rotate

Ручная ротация JWT ключей.

**Требует:** ADMIN роль

#### Тело запроса

```json
{
  "force": false
}
```

#### Ответ 200 OK

```json
{
  "success": true,
  "message": "JWT keys rotated successfully",
  "new_key_version": "660e8400-e29b-41d4-a716-446655440001",
  "deactivated_keys": 1
}
```

---

### GET /jwt-keys/history

Получение истории ротаций JWT ключей.

**Требует:** ADMIN роль

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `limit` | int | Максимальное количество записей (default: 50, max: 100) |

---

## Files API (Internal)

Централизованный реестр файлов (используется Ingester/Query модулями).

### POST /files

Регистрация нового файла в registry.

**Требует:** Service Account с ролью ADMIN или USER

#### Тело запроса

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_filename": "document.pdf",
  "storage_filename": "document_20250127_abc123.pdf",
  "storage_path": "/data/files/2025/01/27",
  "file_size": 1048576,
  "mime_type": "application/pdf",
  "checksum_sha256": "a1b2c3d4e5f6...",
  "retention_policy": "temporary",
  "storage_element_id": "se-01",
  "ttl_days": 30
}
```

#### Ответ 201 Created

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_filename": "document.pdf",
  "retention_policy": "temporary",
  "storage_element_id": "se-01",
  "created_at": "2025-01-27T14:30:45Z",
  "ttl_expires_at": "2025-02-26T14:30:45Z"
}
```

---

### GET /files/{file_id}

Получение метаданных файла.

**Требует:** Service Account (любая роль)

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `include_deleted` | bool | Включать удаленные файлы (требуется ADMIN роль) |

---

### PUT /files/{file_id}

Обновление метаданных файла (финализация).

**Требует:** Service Account с ролью ADMIN или USER

#### Тело запроса

```json
{
  "retention_policy": "permanent",
  "storage_element_id": "se-02",
  "storage_path": "/data/permanent/2025/01/27",
  "finalized_at": "2025-01-27T14:30:45Z"
}
```

---

### DELETE /files/{file_id}

Мягкое удаление файла (soft delete).

**Требует:** Service Account с ролью ADMIN

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `deletion_reason` | string | Причина удаления (manual, ttl_expired, gc_cleanup, finalized) |

---

### GET /files

Получение списка файлов с pagination.

**Требует:** Service Account (любая роль)

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `page` | int | Номер страницы (default: 1) |
| `page_size` | int | Размер страницы (default: 50, max: 1000) |
| `retention_policy` | string | Фильтр: temporary или permanent |
| `storage_element_id` | string | Фильтр по Storage Element |
| `include_deleted` | bool | Включать удаленные (требуется ADMIN роль) |

---

## Internal API

Fallback API для межсервисного взаимодействия (когда Redis недоступен).

### GET /internal/storage-elements/available

Получение списка доступных Storage Elements для записи.

**Требует:** Service Account (OAuth 2.0)

#### Query параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `mode` | string | Фильтр по режиму (edit, rw) |
| `min_free_bytes` | int | Минимальное свободное место |

#### Ответ 200 OK

```json
{
  "storage_elements": [
    {
      "id": 1,
      "element_id": "se-01",
      "name": "Edit Storage",
      "mode": "edit",
      "priority": 10,
      "api_url": "http://se-01:8010",
      "capacity_bytes": 10737418240,
      "used_bytes": 5368709120,
      "health_status": "healthy",
      "capacity_status": "ok"
    }
  ],
  "total": 1
}
```

---

### GET /internal/storage-elements/{element_id}

Получение Storage Element по element_id.

**Требует:** Service Account (OAuth 2.0)

---

## Health API

> **Base URL:** `http://{host}:8000` (без `/api/v1`)

### GET /health/live

Liveness probe — проверка что приложение запущено.

#### Ответ 200 OK

```json
{
  "status": "alive",
  "timestamp": "2025-01-27T14:30:45Z",
  "service": "artstore-admin",
  "version": "0.1.0"
}
```

---

### GET /health/ready

Readiness probe — проверка готовности принимать трафик.

Проверяет:
- PostgreSQL (критично)
- Redis (опционально, degraded mode при недоступности)

#### Ответ 200 OK

```json
{
  "status": "ready",
  "degraded": false,
  "timestamp": "2025-01-27T14:30:45Z",
  "service": "artstore-admin",
  "version": "0.1.0",
  "last_check": "2025-01-27T14:30:40Z",
  "dependencies": {
    "database": {"status": "up", "critical": true},
    "redis": {"status": "up", "critical": false}
  }
}
```

#### Статусы

| Статус | HTTP Code | Описание |
|--------|-----------|----------|
| `ready` | 200 | Все компоненты работают |
| `degraded` | 200 | Redis недоступен, но работа возможна |
| `not_ready` | 503 | БД недоступна |

---

### GET /health/startup

Startup probe — проверка что приложение стартовало.

---

### GET /health/metrics

Prometheus metrics endpoint.

**Требует:** `MONITORING_PROMETHEUS_ENABLED=true`

---

## Модели данных

### AdminRole

```
super_admin | admin | readonly
```

### ServiceAccountRole

```
ADMIN | USER | AUDITOR | READONLY
```

### ServiceAccountStatus

```
ACTIVE | SUSPENDED | EXPIRED | DELETED
```

### StorageMode

```
edit | rw | ro | ar
```

### StorageStatus

```
online | offline | degraded | maintenance
```

### StorageType

```
local | s3
```

### RetentionPolicy

```
temporary | permanent
```

---

## Коды ошибок

| HTTP Code | Описание |
|-----------|----------|
| 200 | Успешный запрос |
| 201 | Ресурс создан |
| 204 | Ресурс удален (no content) |
| 400 | Невалидные параметры запроса |
| 401 | Требуется аутентификация |
| 403 | Недостаточно прав |
| 404 | Ресурс не найден |
| 409 | Конфликт (ресурс уже существует) |
| 423 | Аккаунт заблокирован |
| 500 | Внутренняя ошибка сервера |
| 503 | Сервис недоступен |

### Формат ошибки

```json
{
  "detail": "Error message description"
}
```
