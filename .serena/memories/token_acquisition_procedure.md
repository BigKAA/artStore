# Процедура получения OAuth токена для ArtStore API

## Service Account Credentials

### Основной тестовый аккаунт
- **client_id**: `sa_prod_admin_service_de171928`
- **client_secret**: `TestPassword123!`
- **role**: ADMIN
- **name**: admin-service

### Второй SA (ingester-service)
- **client_id**: `sa_prod_admin_service_66e7f458`
- **client_secret**: неизвестен (нужно смотреть логи при создании)

## Получение токена

### Команда (через heredoc для избежания проблем с escape)
```bash
cat << 'EOFCURL' | bash
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"grant_type": "client_credentials", "client_id": "sa_prod_admin_service_de171928", "client_secret": "TestPassword123!"}'
EOFCURL
```

### Извлечение access_token в переменную
```bash
TOKEN=$(cat << 'EOFCURL' | bash | jq -r '.access_token'
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"grant_type": "client_credentials", "client_id": "sa_prod_admin_service_de171928", "client_secret": "TestPassword123!"}'
EOFCURL
)
```

### Использование токена
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/storage-elements/
```

## Источник credentials

Credentials задаются в `docker-compose.yml`:
```yaml
INITIAL_ACCOUNT_ENABLED: "on"
INITIAL_ACCOUNT_NAME: admin-service
INITIAL_ACCOUNT_ROLE: ADMIN
INITIAL_ACCOUNT_PASSWORD: TestPassword123!
```

## База данных Service Accounts

```bash
docker exec artstore_postgres psql -U artstore -d artstore_admin -t -c \
  "SELECT name, client_id, role, status FROM service_accounts;"
```

## Время жизни токена
- **access_token**: 1800 секунд (30 минут)
- **refresh_token**: 7 дней
- **token_type**: Bearer

## Admin User Login (альтернатива)

Для admin UI используется отдельный endpoint:
```bash
curl -s -X POST http://localhost:8000/api/v1/admin-auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "<password>"}'
```

Пароли admin_users хранятся в `admin_users.password_hash` (bcrypt).
