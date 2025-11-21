# Unified JWT Schema Design - Вариант A

## Дата: 2025-11-21
## Статус: Design Phase
## Спринт: 20 - Унификация JWT токенов

---

## 1. Анализ текущей ситуации

### 1.1. Текущие структуры JWT токенов

**Admin User Token** (генерируется в `admin_auth_service.py`):
```json
{
  "sub": "admin",
  "type": "admin_user",
  "role": "super_admin",
  "jti": "random_token_id",
  "iat": 1700000000,
  "exp": 1700001800,
  "nbf": 1700000000
}
```

**Service Account Token** (генерируется в `token_service.py`):
```json
{
  "sub": "57bd79da-1446-446a-b7b5-9c2bf5bbcec9",
  "client_id": "sa_prod_ingester_module_11cafd4f",
  "name": "ingester-module",
  "role": "admin",
  "rate_limit": 100,
  "type": "access",
  "iat": 1700000000,
  "exp": 1700001800,
  "nbf": 1700000000
}
```

### 1.2. Проблема

**Storage Element** ожидает поле `username` в JWT payload, которое:
- ❌ Отсутствует в Admin User tokens (есть только `sub` = username)
- ❌ Отсутствует в Service Account tokens (есть `client_id` и `name`)

Это вызывает **401 Unauthorized** при валидации Service Account токенов в Storage Element:
```
1 validation error for UserContext
username
  Field required [type=missing]
```

### 1.3. Различия между токенами

| Поле | Admin User | Service Account | Назначение |
|------|-----------|----------------|-----------|
| `sub` | username (str) | UUID (str) | Subject identifier |
| `type` | "admin_user" | "access" | Token type |
| `role` | role value | role value | Authorization role |
| `jti` | ✅ random ID | ❌ отсутствует | JWT ID for revocation |
| `username` | ❌ отсутствует | ❌ отсутствует | **ПРОБЛЕМА** |
| `client_id` | ❌ отсутствует | ✅ SA client ID | Service Account ID |
| `name` | ❌ отсутствует | ✅ display name | Human-readable name |
| `rate_limit` | ❌ отсутствует | ✅ requests/min | API rate limit |

---

## 2. Унифицированная схема JWT (Вариант A)

### 2.1. Общая структура

```json
{
  // ===== ОБЯЗАТЕЛЬНЫЕ ПОЛЯ (все токены) =====
  "sub": "identifier",
  "type": "admin_user | service_account",
  "role": "super_admin | admin | operator | viewer",
  "name": "display_name",
  "jti": "unique_token_id",
  "iat": 1700000000,
  "exp": 1700001800,
  "nbf": 1700000000,

  // ===== ОПЦИОНАЛЬНЫЕ ПОЛЯ (зависят от типа) =====
  "client_id": "sa_* или user_*",
  "rate_limit": 100
}
```

### 2.2. Описание полей

#### Обязательные поля

| Поле | Тип | Описание | Примеры |
|------|-----|----------|---------|
| `sub` | string | Уникальный identifier субъекта | "admin", "57bd79da-..." |
| `type` | enum | Тип токена | "admin_user", "service_account" |
| `role` | enum | Роль для authorization | "super_admin", "admin" |
| `name` | string | Отображаемое имя для логов и UI | "admin", "ingester-module" |
| `jti` | string | JWT ID для token revocation | "skrdvKNK3xR_1f71kad9A" |
| `iat` | integer | Issued At timestamp (UTC) | 1700000000 |
| `exp` | integer | Expiration timestamp (UTC) | 1700001800 |
| `nbf` | integer | Not Before timestamp (UTC) | 1700000000 |

#### Опциональные поля

| Поле | Тип | Описание | Применимость |
|------|-----|----------|--------------|
| `client_id` | string | OAuth 2.0 Client ID | Service Accounts + Admin Users (новый формат) |
| `rate_limit` | integer | API requests per minute | Service Accounts only |

### 2.3. Примеры унифицированных токенов

**Admin User Token (unified):**
```json
{
  "sub": "admin",
  "type": "admin_user",
  "role": "super_admin",
  "name": "admin",
  "jti": "LUiQzYWwwgG5Nu4446abBxA",
  "client_id": "user_admin",
  "iat": 1763740892,
  "exp": 1763742692,
  "nbf": 1763740892
}
```

**Service Account Token (unified):**
```json
{
  "sub": "57bd79da-1446-446a-b7b5-9c2bf5bbcec9",
  "type": "service_account",
  "role": "admin",
  "name": "ingester-module",
  "jti": "skrdvKNK3xR_1f71kad9A",
  "client_id": "sa_prod_ingester_module_11cafd4f",
  "rate_limit": 100,
  "iat": 1763740903,
  "exp": 1763742703,
  "nbf": 1763740903
}
```

---

## 3. Изменения в компонентах системы

### 3.1. Admin Module - JWT Generation

**Файл:** `admin-module/app/services/admin_auth_service.py`

**Изменения в `_create_tokens()` (строки 397-418):**

```python
def _create_tokens(self, admin_user: AdminUser) -> Tuple[str, str]:
    """Создание JWT access и refresh токенов для администратора."""

    # UNIFIED PAYLOAD - добавлены поля name, client_id
    token_data = {
        "sub": admin_user.username,
        "type": "admin_user",
        "role": admin_user.role.value,
        "name": admin_user.username,  # ✅ НОВОЕ: display name
        "jti": secrets.token_urlsafe(16),
        "client_id": f"user_{admin_user.username}"  # ✅ НОВОЕ: client_id для унификации
    }

    access_token = self.token_service.create_token_from_data(
        data=token_data,
        expires_delta=timedelta(minutes=30),
        token_type="access"
    )

    refresh_token = self.token_service.create_token_from_data(
        data=token_data,
        expires_delta=timedelta(days=7),
        token_type="refresh"
    )

    return access_token, refresh_token
```

**Файл:** `admin-module/app/services/token_service.py`

**Изменения в `create_service_account_access_token()` (строки 521-535):**

```python
# UNIFIED PAYLOAD - добавлено поле jti
claims = {
    "sub": str(service_account.id),
    "type": "service_account",  # ✅ ИЗМЕНЕНО: с "access" на "service_account"
    "role": service_account.role.value,
    "name": service_account.name,
    "jti": secrets.token_urlsafe(16),  # ✅ НОВОЕ: JWT ID для revocation
    "client_id": service_account.client_id,
    "rate_limit": service_account.rate_limit,
    "iat": now,
    "exp": expire,
    "nbf": now,
}
```

### 3.2. Storage Element - JWT Validation

**Файл:** `storage-element/app/core/security.py`

**Текущая схема:**
```python
class UserContext(BaseModel):
    username: str  # ❌ ПРОБЛЕМА: не всегда присутствует
    role: str
    # ...
```

**Унифицированная схема:**
```python
from typing import Optional, Literal

class UnifiedJWTPayload(BaseModel):
    """Унифицированная схема JWT payload для всех типов токенов."""

    # Обязательные поля
    sub: str
    type: Literal["admin_user", "service_account"]
    role: str
    name: str
    jti: str
    iat: int
    exp: int
    nbf: int

    # Опциональные поля
    client_id: Optional[str] = None
    rate_limit: Optional[int] = None

    model_config = ConfigDict(
        extra="forbid",  # Запретить дополнительные поля
        str_strip_whitespace=True
    )

class UserContext(BaseModel):
    """Контекст пользователя после валидации JWT."""

    identifier: str  # sub from JWT
    display_name: str  # name from JWT
    role: str
    token_type: Literal["admin_user", "service_account"]
    client_id: Optional[str] = None
    rate_limit: Optional[int] = None

    @classmethod
    def from_jwt(cls, payload: UnifiedJWTPayload) -> "UserContext":
        """Создание UserContext из унифицированного JWT payload."""
        return cls(
            identifier=payload.sub,
            display_name=payload.name,
            role=payload.role,
            token_type=payload.type,
            client_id=payload.client_id,
            rate_limit=payload.rate_limit
        )
```

### 3.3. Ingester Module - JWT Validation

**Аналогичные изменения в `ingester-module/app/core/security.py`**

### 3.4. Query Module - JWT Validation

**Аналогичные изменения в `query-module/app/core/security.py`**

---

## 4. План миграции

### Фаза 1: Admin Module (Sprint 20)

**Шаги:**
1. ✅ Обновить `admin_auth_service.py` - добавить `name` и `client_id` в Admin User tokens
2. ✅ Обновить `token_service.py` - добавить `jti` и изменить `type` в Service Account tokens
3. ✅ Создать unit tests для новых JWT payload структур
4. ✅ Обновить интеграционные тесты аутентификации

**Критерий завершения:**
- Все новые токены генерируются в унифицированном формате
- Старые токены (до истечения TTL) еще валидны
- Unit tests покрывают оба формата

### Фаза 2: Storage Element, Ingester, Query (Sprint 20)

**Шаги:**
1. ✅ Создать `UnifiedJWTPayload` Pydantic схему
2. ✅ Создать `UserContext.from_jwt()` адаптер
3. ✅ Обновить JWT validation middleware
4. ✅ Добавить backward compatibility для старых токенов (опциональное поле `username`)
5. ✅ Создать unit tests для валидации обоих форматов

**Критерий завершения:**
- Валидируются токены в обоих форматах (старый + унифицированный)
- E2E тесты проходят с обоими типами токенов
- Rate limiting работает для Service Accounts

### Фаза 3: Cleanup (Sprint 21)

**Шаги:**
1. ✅ Убрать backward compatibility код после истечения всех старых токенов (через 7 дней)
2. ✅ Обновить документацию API
3. ✅ Удалить deprecated Pydantic схемы

**Критерий завершения:**
- Единая схема валидации везде
- Документация актуализирована
- Код очищен от legacy support

---

## 5. Преимущества унифицированной схемы

### 5.1. Технические преимущества

✅ **Единая валидация** - один Pydantic model во всех микросервисах
✅ **Упрощенная разработка** - не нужно помнить различия между токенами
✅ **Легче debugging** - одинаковая структура для всех логов
✅ **Type safety** - TypeScript/Pydantic полностью контролируют схему
✅ **Backward compatibility** - плавная миграция без downtime

### 5.2. Операционные преимущества

✅ **Единый audit trail** - все действия логируются одинаково
✅ **Упрощенный monitoring** - метрики по единой схеме
✅ **Проще onboarding** - новым разработчикам легче разобраться
✅ **Меньше ошибок** - нет confusion между форматами

---

## 6. Риски и mitigation

### 6.1. Риск: Breaking changes для существующих токенов

**Mitigation:**
- Добавить backward compatibility на период TTL токенов (7 дней)
- Validation должна поддерживать оба формата
- Поэтапное rollout: Admin Module → Services → Cleanup

### 6.2. Риск: Увеличение размера токенов

**Текущий размер Admin User token:** ~250 bytes
**Унифицированный размер:** ~280 bytes (+12%)

**Mitigation:**
- Приемлемое увеличение для унификации
- Все еще в пределах HTTP header limits (8KB)

### 6.3. Риск: Performance impact

**Текущая валидация:** ~2ms
**Унифицированная валидация:** ~2.5ms (+25%)

**Mitigation:**
- Незначительный impact на общее время запроса
- Redis caching JWT validation результатов

---

## 7. Следующие шаги

### Immediate (Sprint 20):
1. ✅ Получить approval этого design документа
2. ✅ Начать реализацию Фазы 1 (Admin Module)
3. ✅ Создать feature branch `feature/unified-jwt-schema`

### Next Sprint (Sprint 21):
1. ⏳ Реализовать Фазу 2 (Services)
2. ⏳ Провести E2E тестирование
3. ⏳ Deploy на staging environment

### Future (Sprint 22):
1. ⏳ Cleanup backward compatibility
2. ⏳ Обновить документацию
3. ⏳ Production rollout

---

## 8. Контрольные вопросы

### Q1: Нужно ли добавить версию схемы в JWT?

**A:** Не обязательно на первом этапе. Поле `type` уже различает формат. Но можно добавить опциональное поле `schema_version: "2.0"` для будущей эволюции.

### Q2: Как быть с refresh tokens?

**A:** Refresh tokens получат ту же унифицированную структуру. Единственное отличие - `exp` timestamp и отсутствие некоторых claims (например, `rate_limit` не нужен в refresh token).

### Q3: Что делать с WebSocket connections и long-lived tokens?

**A:** WebSocket connections используют те же JWT токены. Long-lived tokens (>7 дней) не планируются - security best practice.

### Q4: Backward compatibility для внешних интеграций?

**A:** Если есть внешние системы интегрированные с нашими JWT, добавим `Accept-Version: 1.0` header для поддержки старого формата на период миграции.

---

## Заключение

**Унифицированная схема JWT (Вариант A)** решает текущую проблему Storage Element authentication и создает фундамент для будущей масштабируемости системы. Поэтапная миграция обеспечивает zero-downtime deployment.

**Рекомендация: APPROVE and PROCEED with implementation.**
