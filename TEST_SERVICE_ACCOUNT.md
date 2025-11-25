# Test Service Account - Руководство

Этот документ описывает тестовый service account для интеграционного тестирования модулей ArtStore.

## Credentials

**ВАЖНО:** Используйте только для development/testing окружения!

```yaml
Name: test-integration-service
Client ID: sa_dev_test_integration_ser_1ea5433c
Client Secret: 6vj(mpptg.C+(9WZ
Role: user
Rate Limit: 1000 req/min
Environment: dev
Status: active
Secret Expires: 2026-02-23
```

## Использование

### 1. Получение Access Token

**Endpoint:** `POST http://localhost:8000/api/v1/auth/token`

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "sa_dev_test_integration_ser_1ea5433c",
    "client_secret": "6vj(mpptg.C+(9WZ"
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

### 2. Использование Access Token

Добавьте токен в заголовок `Authorization` для всех API запросов:

```bash
curl -X GET http://localhost:8010/api/v1/files \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Примеры для разных модулей

### Storage Element (port 8010)

**Upload файла:**
```bash
TOKEN="YOUR_ACCESS_TOKEN"

curl -X POST http://localhost:8010/api/v1/files \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/file.txt" \
  -F "retention_days=90"
```

**List файлов:**
```bash
curl -X GET http://localhost:8010/api/v1/files \
  -H "Authorization: Bearer $TOKEN"
```

**Download файла:**
```bash
curl -X GET http://localhost:8010/api/v1/files/{file_id}/download \
  -H "Authorization: Bearer $TOKEN" \
  -o downloaded_file.txt
```

### Ingester Module (port 8020)

**Streaming upload:**
```bash
TOKEN="YOUR_ACCESS_TOKEN"

curl -X POST http://localhost:8020/api/v1/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@large_file.zip" \
  -F "compress=true" \
  -F "retention_days=180"
```

### Query Module (port 8030)

**Search файлов:**
```bash
TOKEN="YOUR_ACCESS_TOKEN"

curl -X GET "http://localhost:8030/api/v1/search?query=report&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

**Advanced search with filters:**
```bash
curl -X POST http://localhost:8030/api/v1/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "financial report",
    "content_type": "application/pdf",
    "date_from": "2025-01-01",
    "date_to": "2025-12-31",
    "size_min": 1024,
    "size_max": 10485760
  }'
```

## Integration Tests

### Python Example (pytest)

```python
import pytest
import requests

# Test Service Account credentials
TEST_CLIENT_ID = "sa_dev_test_integration_ser_1ea5433c"
TEST_CLIENT_SECRET = "6vj(mpptg.C+(9WZ"
AUTH_URL = "http://localhost:8000/api/v1/auth/token"


@pytest.fixture(scope="session")
def auth_token():
    """Получение access token для всех тестов."""
    response = requests.post(
        AUTH_URL,
        json={
            "grant_type": "client_credentials",
            "client_id": TEST_CLIENT_ID,
            "client_secret": TEST_CLIENT_SECRET
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_upload_file(auth_token):
    """Тест загрузки файла в Storage Element."""
    url = "http://localhost:8010/api/v1/files"
    headers = {"Authorization": f"Bearer {auth_token}"}

    with open("test_file.txt", "rb") as f:
        files = {"file": f}
        data = {"retention_days": 90}

        response = requests.post(url, headers=headers, files=files, data=data)

    assert response.status_code == 201
    file_data = response.json()
    assert "id" in file_data
    assert "filename" in file_data

    return file_data["id"]


def test_search_file(auth_token):
    """Тест поиска файлов через Query Module."""
    url = "http://localhost:8030/api/v1/search"
    headers = {"Authorization": f"Bearer {auth_token}"}
    params = {"query": "test", "limit": 10}

    response = requests.get(url, headers=headers, params=params)

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)
```

### JavaScript Example (Jest)

```javascript
const axios = require('axios');

const TEST_CLIENT_ID = 'sa_dev_test_integration_ser_1ea5433c';
const TEST_CLIENT_SECRET = '6vj(mpptg.C+(9WZ';
const AUTH_URL = 'http://localhost:8000/api/v1/auth/token';

let authToken;

beforeAll(async () => {
  // Получение access token перед всеми тестами
  const response = await axios.post(AUTH_URL, {
    grant_type: 'client_credentials',
    client_id: TEST_CLIENT_ID,
    client_secret: TEST_CLIENT_SECRET
  });

  authToken = response.data.access_token;
});

describe('Storage Element API', () => {
  test('should upload file successfully', async () => {
    const FormData = require('form-data');
    const fs = require('fs');

    const form = new FormData();
    form.append('file', fs.createReadStream('test_file.txt'));
    form.append('retention_days', '90');

    const response = await axios.post(
      'http://localhost:8010/api/v1/files',
      form,
      {
        headers: {
          ...form.getHeaders(),
          'Authorization': `Bearer ${authToken}`
        }
      }
    );

    expect(response.status).toBe(201);
    expect(response.data).toHaveProperty('id');
    expect(response.data).toHaveProperty('filename');
  });

  test('should list files successfully', async () => {
    const response = await axios.get(
      'http://localhost:8010/api/v1/files',
      {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      }
    );

    expect(response.status).toBe(200);
    expect(response.data).toHaveProperty('items');
    expect(Array.isArray(response.data.items)).toBe(true);
  });
});
```

## Permissions

Service Account имеет роль **USER**, что дает доступ к:

✅ **Разрешено:**
- Загрузка файлов (Storage Element, Ingester Module)
- Чтение файлов (Storage Element, Query Module)
- Поиск по метаданным (Query Module)
- Скачивание файлов (Storage Element, Query Module)

❌ **Запрещено:**
- Изменение режимов Storage Element (требуется ADMIN)
- Управление другими Service Accounts (требуется ADMIN)
- Удаление файлов из archive mode (требуется ADMIN)
- Изменение конфигурации системы (требуется ADMIN)

## Rate Limiting

- **Лимит:** 1000 запросов в минуту
- **Burst:** До 1500 запросов кратковременно
- **Действие при превышении:** HTTP 429 Too Many Requests

## Troubleshooting

### Проблема: "Invalid client_id or client_secret"

**Причина:** Неверные credentials или истек срок действия secret.

**Решение:**
1. Проверьте client_id и client_secret
2. Проверьте срок действия: `secret_expires_at: 2026-02-23`
3. При необходимости создайте новый service account

### Проблема: "Token expired"

**Причина:** Access token действителен только 30 минут.

**Решение:**
1. Запросите новый access token через `/api/v1/auth/token`
2. Используйте refresh token для обновления
3. В тестах используйте fixture/hook для автоматического обновления

### Проблема: HTTP 429 Too Many Requests

**Причина:** Превышен rate limit (1000 req/min).

**Решение:**
1. Добавьте задержки между запросами в тестах
2. Используйте батчинг для групповых операций
3. При необходимости запросите увеличение rate limit у администратора

## Security Notes

⚠️ **ВАЖНО:**

1. **НЕ используйте** этот service account в production!
2. **НЕ коммитьте** credentials в публичные репозитории
3. **Ротируйте** secret регулярно (каждые 90 дней рекомендуется)
4. **Используйте** environment variables для хранения credentials в CI/CD

### Пример для CI/CD

```yaml
# GitHub Actions
env:
  TEST_SERVICE_ACCOUNT_CLIENT_ID: ${{ secrets.TEST_CLIENT_ID }}
  TEST_SERVICE_ACCOUNT_CLIENT_SECRET: ${{ secrets.TEST_CLIENT_SECRET }}

# GitLab CI
variables:
  TEST_SERVICE_ACCOUNT_CLIENT_ID: ${CI_TEST_CLIENT_ID}
  TEST_SERVICE_ACCOUNT_CLIENT_SECRET: ${CI_TEST_CLIENT_SECRET}
```

## Создание нового Service Account

Если нужно создать новый тестовый service account:

```bash
# 1. Получить admin token
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/admin-auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | jq -r '.access_token')

# 2. Создать новый service account
curl -X POST http://localhost:8000/api/v1/service-accounts/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "new-test-service",
    "description": "New test service account",
    "role": "user",
    "rate_limit": 1000,
    "environment": "dev"
  }' | jq .

# ВАЖНО: client_secret отображается ТОЛЬКО при создании!
# Сохраните его в безопасном месте.
```

## Контакты

При возникновении проблем или вопросов:
- Проверьте документацию: `README.md`, `DEVELOPMENT-GUIDE.md`
- Проверьте логи Admin Module: `docker-compose logs -f admin-module`
- Создайте issue в репозитории проекта
