# Документация по механизмам аутентификации

## Основной документ

**Файл**: `admin-module/AUTH-MECHANICS.md`

## Когда обращаться к этому документу

Обращайся к `admin-module/AUTH-MECHANICS.md` когда:

1. **Нужно понять процесс аутентификации** — документ содержит полное описание двух систем аутентификации (Admin User и Service Account)

2. **Работа с JWT токенами** — структура payload, время жизни токенов, процесс refresh

3. **Реализация защищённых endpoints** — описание FastAPI dependencies для аутентификации

4. **Работа с OAuth 2.0 Client Credentials** — процесс получения токена для Service Account

5. **Отладка проблем аутентификации** — диаграммы потоков, примеры запросов/ответов

6. **Понимание RBAC** — роли Admin Users и Service Accounts, механизм RoleChecker

7. **Ротация secrets/ключей** — описание механизмов ротации JWT ключей и Service Account secrets

## Ключевые концепции из документа

### Два типа аутентификации
- **Admin User** (Human-to-Machine): `/api/v1/admin-auth/*` — username/password → JWT
- **Service Account** (Machine-to-Machine): `/api/v1/auth/token` — OAuth 2.0 Client Credentials

### JWT Payload
- `type: "admin_user"` или `type: "service_account"` — определяет тип токена
- `jti` — JWT ID для будущей token revocation
- `client_id` — унифицированный идентификатор

### Ключевые файлы
- `app/api/v1/endpoints/auth.py` — Service Account token endpoint
- `app/api/v1/endpoints/admin_auth.py` — Admin User login/refresh/logout
- `app/services/token_service.py` — JWT создание и валидация
- `app/api/dependencies/admin_auth.py` — FastAPI dependencies

### Известные ограничения
- Logout только client-side (нет Redis blacklist для jti)
- Refresh token для Service Account выдаётся, но нет endpoint для использования
- Rate limiting хранится в токене, но нет middleware для enforcement

## Связанные документы
- `README.md` (корень) — ссылка на AUTH-MECHANICS.md в разделе типов учётных записей
- `admin-module/README.md` — общая документация Admin Module
