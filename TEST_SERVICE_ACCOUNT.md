# Test Service Account - Руководство

Документ описывает тестовые service accounts для development/testing окружения ArtStore.

## Основной Service Account (ADMIN)

**Источник**: `docker-compose.yml` → `INITIAL_ACCOUNT_*`

```yaml
Name: admin-service
Client ID: sa_prod_admin_service_de171928
Client Secret: TestPassword123!
Role: ADMIN
Rate Limit: 1000 req/min
```

> **Примечание**: `client_id` генерируется автоматически при первом запуске Admin Module.
> Если база данных была пересоздана, `client_id` изменится!

## Получение Access Token

### Быстрая команда

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"grant_type":"client_credentials","client_id":"sa_prod_admin_service_de171928","client_secret":"TestPassword123!"}' \
  | jq -r '.access_token')
```

### Полный запрос

**Endpoint:** `POST http://localhost:8000/api/v1/auth/token`

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "sa_prod_admin_service_de171928",
    "client_secret": "TestPassword123!"
  }'
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

## Использование токена

### Порты модулей

| Модуль | Порт | Описание |
|--------|------|----------|
| Admin Module | 8000 | Управление, аутентификация |
| Storage Element | 8010 | Хранение файлов |
| Ingester Module | 8020 | Загрузка файлов |
| Query Module | 8030 | Поиск и скачивание |

### Примеры запросов

```bash
# Admin Module - список Storage Elements
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/storage-elements/

# Storage Element - список файлов
curl -H "Authorization: Bearer $TOKEN" http://localhost:8010/api/v1/files/

# Ingester Module - health check
curl -H "Authorization: Bearer $TOKEN" http://localhost:8020/api/v1/health/ready

# Query Module - поиск
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8030/api/v1/search?query=test"
```

## Права доступа (Role: ADMIN)

**Разрешено:**
- Все операции с файлами (CRUD)
- Управление Storage Elements
- Изменение режимов SE (edit → rw → ro → ar)
- Создание других Service Accounts

## Параметры токена

| Параметр | Значение |
|----------|----------|
| Access Token TTL | 30 минут |
| Refresh Token TTL | 7 дней |
| Algorithm | RS256 |

## Troubleshooting

### Ошибка: "Invalid client_id or client_secret"

1. Проверьте актуальный `client_id` в БД:
```bash
docker exec artstore_postgres psql -U artstore -d artstore_admin -t -c \
  "SELECT name, client_id FROM service_accounts WHERE name='admin-service';"
```

2. Если `client_id` отличается, используйте актуальный из БД.

### Ошибка: "Token expired"

Токен действителен 30 минут. Получите новый:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"grant_type":"client_credentials","client_id":"sa_prod_admin_service_de171928","client_secret":"TestPassword123!"}' \
  | jq -r '.access_token')
```

### Ошибка: HTTP 429 Too Many Requests

Rate limit превышен (1000 req/min). Добавьте задержки между запросами.

## Создание дополнительного Service Account

```bash
# Требуется ADMIN токен
curl -X POST http://localhost:8000/api/v1/service-accounts/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-test-service",
    "description": "Test service account",
    "role": "user",
    "rate_limit": 100
  }'

# ВАЖНО: client_secret отображается ТОЛЬКО при создании!
```

## Security Notes

- **НЕ используйте** эти credentials в production!
- **НЕ коммитьте** реальные secrets в репозиторий
- Для CI/CD используйте environment variables

## См. также

- `admin-module/AUTH-MECHANICS.md` - детальная архитектура аутентификации
- `CLAUDE.md` - инструкции для разработки
- `docker-compose.yml` - конфигурация `INITIAL_ACCOUNT_*`
