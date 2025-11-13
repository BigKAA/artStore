# ArtStore API Migration Guide
## Переход с User Authentication на OAuth 2.0 Service Accounts

**Версия**: 1.0
**Дата публикации**: 2025-01-12
**Срок миграции**: 4 недели (Weeks 7-10)
**Статус**: ОБЯЗАТЕЛЬНАЯ МИГРАЦИЯ

---

## Executive Summary

ArtStore переходит с модели аутентификации через пользовательские аккаунты (LDAP) на **OAuth 2.0 Client Credentials flow** для Service Accounts. Это изменение отражает фактическое использование системы: **машина-к-машине (M2M) коммуникация**, а не прямое использование конечными пользователями.

### Ключевые изменения

| Aspect | Старый метод (deprecated) | Новый метод (required) |
|--------|---------------------------|------------------------|
| **Endpoint** | `POST /api/auth/login` | `POST /api/auth/token` |
| **Credentials** | `username` + `password` | `client_id` + `client_secret` |
| **Entity Type** | User (LDAP-backed) | Service Account |
| **Flow** | Username/Password Auth | OAuth 2.0 Client Credentials |
| **Token Claims** | `username`, `email`, `ldap_groups` | `client_id`, `role`, `rate_limit` |

### Преимущества миграции

✅ **Упрощение**: Удаление зависимости от LDAP инфраструктуры
✅ **Безопасность**: Industry-standard OAuth 2.0 для M2M аутентификации
✅ **Производительность**: Устранение LDAP query latency
✅ **Управляемость**: Централизованное управление Service Accounts через API
✅ **Rate Limiting**: Встроенная защита от перегрузки на уровне клиента

---

## Timeline

### Week 7 (2025-01-15 - 2025-01-21): Notification Period
- ✅ Migration guide distribution (this document)
- ✅ Dual running period begins (both auth methods active)
- ✅ Support channel setup (#artstore-migration on Slack)

### Week 8-9 (2025-01-22 - 2025-02-04): Active Migration
- 🔄 Clients migrate to new authentication method
- 🔄 ArtStore team monitors adoption metrics
- 🔄 Support for migration issues

### Week 10 (2025-02-05 - 2025-02-11): Verification
- ✅ Target: 100% clients migrated
- ✅ Validation: Zero `/api/auth/login` usage for 7 days
- ⚠️ Warning: Old auth method will be disabled after this week

### Week 11+ (2025-02-12+): Cleanup
- ❌ `/api/auth/login` endpoint REMOVED
- ❌ User model deprecated
- ❌ LDAP infrastructure decommissioned

---

## Migration Steps

### Step 1: Получение Service Account Credentials

Обратитесь к администратору ArtStore для создания Service Account для вашего приложения.

**Администратор выполнит**:
```bash
POST /api/service-accounts
{
  "name": "MyApp Production Client",
  "role": "USER",  # or "ADMIN", "AUDITOR", "READONLY"
  "rate_limit": 100  # requests per minute
}
```

**Вы получите**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "MyApp Production Client",
  "client_id": "sa_prod_myapp_a1b2c3d4",
  "client_secret": "secret_XyZ123...ABC789",
  "role": "USER",
  "rate_limit": 100,
  "status": "ACTIVE",
  "created_at": "2025-01-15T10:00:00Z"
}
```

**⚠️ ВАЖНО**:
- `client_secret` отображается **ТОЛЬКО ОДИН РАЗ** при создании
- Сохраните его в защищенном хранилище (Vault, AWS Secrets Manager, Azure Key Vault)
- Никогда не храните в коде или конфигурационных файлах в plaintext

### Step 2: Обновление Authentication Logic

#### Старый метод (deprecated)
```python
import requests

# ❌ DEPRECATED - будет удален в Week 11
response = requests.post(
    "https://artstore.example.com/api/auth/login",
    json={
        "username": "myapp_user",
        "password": "MySecretPassword123"
    }
)

if response.status_code == 200:
    access_token = response.json()["access_token"]
    refresh_token = response.json()["refresh_token"]
```

#### Новый метод (required)
```python
import requests
import os

# ✅ REQUIRED - OAuth 2.0 Client Credentials Flow
client_id = os.getenv("ARTSTORE_CLIENT_ID")
client_secret = os.getenv("ARTSTORE_CLIENT_SECRET")

response = requests.post(
    "https://artstore.example.com/api/auth/token",
    json={
        "client_id": client_id,
        "client_secret": client_secret
    },
    headers={
        "Content-Type": "application/json"
    }
)

if response.status_code == 200:
    access_token = response.json()["access_token"]
    refresh_token = response.json()["refresh_token"]
    expires_in = response.json()["expires_in"]  # seconds
```

### Step 3: Обновление Token Usage

JWT токены используются **идентично** старому методу:

```python
# Authenticated API request (no changes)
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

response = requests.get(
    "https://artstore.example.com/api/files/search",
    headers=headers,
    params={"query": "contract"}
)
```

### Step 4: Token Refresh Logic

**Refresh token flow остается неизменным**:

```python
# Same for both old and new auth methods
response = requests.post(
    "https://artstore.example.com/api/auth/refresh",
    json={
        "refresh_token": refresh_token
    }
)

if response.status_code == 200:
    access_token = response.json()["access_token"]
    # refresh_token may also be rotated
    refresh_token = response.json().get("refresh_token", refresh_token)
```

### Step 5: Error Handling

Обновите обработку ошибок аутентификации:

```python
try:
    response = requests.post(
        "https://artstore.example.com/api/auth/token",
        json={
            "client_id": client_id,
            "client_secret": client_secret
        },
        timeout=10
    )
    response.raise_for_status()

except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        # Invalid credentials
        print("Authentication failed: Invalid client_id or client_secret")
    elif e.response.status_code == 403:
        # Account suspended
        print("Service Account suspended. Contact administrator.")
    elif e.response.status_code == 429:
        # Rate limit exceeded
        print("Rate limit exceeded. Retry after:", e.response.headers.get("Retry-After"))
    else:
        print(f"Authentication error: {e}")

except requests.exceptions.Timeout:
    print("Authentication timeout. Check network connectivity.")
```

---

## Code Examples

### Python (requests library)

```python
import os
import requests
from datetime import datetime, timedelta

class ArtStoreClient:
    def __init__(self, base_url, client_id, client_secret):
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None

    def authenticate(self):
        """OAuth 2.0 Client Credentials authentication"""
        response = requests.post(
            f"{self.base_url}/api/auth/token",
            json={
                "client_id": self.client_id,
                "client_secret": self.client_secret
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]

        # Calculate token expiration time
        expires_in = data["expires_in"]  # seconds
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

    def refresh_access_token(self):
        """Refresh expired access token"""
        response = requests.post(
            f"{self.base_url}/api/auth/refresh",
            json={"refresh_token": self.refresh_token},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]

        # Refresh token may be rotated
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        expires_in = data["expires_in"]
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

    def ensure_authenticated(self):
        """Ensure valid access token, refresh if needed"""
        if self.access_token is None:
            self.authenticate()
        elif datetime.now() >= self.token_expires_at:
            self.refresh_access_token()

    def request(self, method, endpoint, **kwargs):
        """Make authenticated API request"""
        self.ensure_authenticated()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"

        response = requests.request(
            method,
            f"{self.base_url}{endpoint}",
            headers=headers,
            **kwargs
        )

        # Handle token expiration during request
        if response.status_code == 401:
            self.refresh_access_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = requests.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=headers,
                **kwargs
            )

        response.raise_for_status()
        return response

# Usage
client = ArtStoreClient(
    base_url="https://artstore.example.com",
    client_id=os.getenv("ARTSTORE_CLIENT_ID"),
    client_secret=os.getenv("ARTSTORE_CLIENT_SECRET")
)

# Search files
response = client.request("GET", "/api/files/search", params={"query": "contract"})
files = response.json()

# Upload file
with open("document.pdf", "rb") as f:
    response = client.request(
        "POST",
        "/api/files/upload",
        files={"file": f},
        data={"retention": "5y"}
    )
```

### Node.js (axios)

```javascript
const axios = require('axios');

class ArtStoreClient {
  constructor(baseUrl, clientId, clientSecret) {
    this.baseUrl = baseUrl;
    this.clientId = clientId;
    this.clientSecret = clientSecret;
    this.accessToken = null;
    this.refreshToken = null;
    this.tokenExpiresAt = null;
  }

  async authenticate() {
    const response = await axios.post(`${this.baseUrl}/api/auth/token`, {
      client_id: this.clientId,
      client_secret: this.clientSecret
    }, {
      headers: { 'Content-Type': 'application/json' },
      timeout: 10000
    });

    this.accessToken = response.data.access_token;
    this.refreshToken = response.data.refresh_token;

    // Calculate expiration time
    const expiresIn = response.data.expires_in * 1000; // convert to ms
    this.tokenExpiresAt = Date.now() + expiresIn;
  }

  async refreshAccessToken() {
    const response = await axios.post(`${this.baseUrl}/api/auth/refresh`, {
      refresh_token: this.refreshToken
    }, {
      timeout: 10000
    });

    this.accessToken = response.data.access_token;

    if (response.data.refresh_token) {
      this.refreshToken = response.data.refresh_token;
    }

    const expiresIn = response.data.expires_in * 1000;
    this.tokenExpiresAt = Date.now() + expiresIn;
  }

  async ensureAuthenticated() {
    if (!this.accessToken) {
      await this.authenticate();
    } else if (Date.now() >= this.tokenExpiresAt) {
      await this.refreshAccessToken();
    }
  }

  async request(method, endpoint, config = {}) {
    await this.ensureAuthenticated();

    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${this.accessToken}`;
    config.baseURL = this.baseUrl;

    try {
      const response = await axios.request({
        method,
        url: endpoint,
        ...config
      });
      return response;
    } catch (error) {
      // Handle token expiration
      if (error.response?.status === 401) {
        await this.refreshAccessToken();
        config.headers.Authorization = `Bearer ${this.accessToken}`;
        return await axios.request({
          method,
          url: endpoint,
          ...config
        });
      }
      throw error;
    }
  }
}

// Usage
const client = new ArtStoreClient(
  'https://artstore.example.com',
  process.env.ARTSTORE_CLIENT_ID,
  process.env.ARTSTORE_CLIENT_SECRET
);

// Search files
const searchResponse = await client.request('GET', '/api/files/search', {
  params: { query: 'contract' }
});
console.log(searchResponse.data);
```

### Java (Spring RestTemplate)

```java
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.HttpClientErrorException;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class ArtStoreClient {
    private final String baseUrl;
    private final String clientId;
    private final String clientSecret;
    private final RestTemplate restTemplate;

    private String accessToken;
    private String refreshToken;
    private Instant tokenExpiresAt;

    public ArtStoreClient(String baseUrl, String clientId, String clientSecret) {
        this.baseUrl = baseUrl;
        this.clientId = clientId;
        this.clientSecret = clientSecret;
        this.restTemplate = new RestTemplate();
    }

    public void authenticate() {
        String url = baseUrl + "/api/auth/token";

        Map<String, String> requestBody = new HashMap<>();
        requestBody.put("client_id", clientId);
        requestBody.put("client_secret", clientSecret);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<Map<String, String>> entity = new HttpEntity<>(requestBody, headers);

        ResponseEntity<Map> response = restTemplate.postForEntity(url, entity, Map.class);
        Map<String, Object> data = response.getBody();

        this.accessToken = (String) data.get("access_token");
        this.refreshToken = (String) data.get("refresh_token");

        Integer expiresIn = (Integer) data.get("expires_in");
        this.tokenExpiresAt = Instant.now().plusSeconds(expiresIn);
    }

    public void refreshAccessToken() {
        String url = baseUrl + "/api/auth/refresh";

        Map<String, String> requestBody = new HashMap<>();
        requestBody.put("refresh_token", refreshToken);

        HttpEntity<Map<String, String>> entity = new HttpEntity<>(requestBody);

        ResponseEntity<Map> response = restTemplate.postForEntity(url, entity, Map.class);
        Map<String, Object> data = response.getBody();

        this.accessToken = (String) data.get("access_token");

        if (data.containsKey("refresh_token")) {
            this.refreshToken = (String) data.get("refresh_token");
        }

        Integer expiresIn = (Integer) data.get("expires_in");
        this.tokenExpiresAt = Instant.now().plusSeconds(expiresIn);
    }

    public void ensureAuthenticated() {
        if (accessToken == null) {
            authenticate();
        } else if (Instant.now().isAfter(tokenExpiresAt)) {
            refreshAccessToken();
        }
    }

    public <T> ResponseEntity<T> request(HttpMethod method, String endpoint,
                                         Object body, Class<T> responseType) {
        ensureAuthenticated();

        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(accessToken);
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<?> entity = new HttpEntity<>(body, headers);

        try {
            return restTemplate.exchange(
                baseUrl + endpoint,
                method,
                entity,
                responseType
            );
        } catch (HttpClientErrorException.Unauthorized e) {
            // Token expired during request, refresh and retry
            refreshAccessToken();
            headers.setBearerAuth(accessToken);
            entity = new HttpEntity<>(body, headers);

            return restTemplate.exchange(
                baseUrl + endpoint,
                method,
                entity,
                responseType
            );
        }
    }
}

// Usage
ArtStoreClient client = new ArtStoreClient(
    "https://artstore.example.com",
    System.getenv("ARTSTORE_CLIENT_ID"),
    System.getenv("ARTSTORE_CLIENT_SECRET")
);

// Search files
ResponseEntity<Map> response = client.request(
    HttpMethod.GET,
    "/api/files/search?query=contract",
    null,
    Map.class
);
```

---

## API Reference

### POST /api/auth/token
**OAuth 2.0 Client Credentials Grant**

#### Request
```http
POST /api/auth/token HTTP/1.1
Host: artstore.example.com
Content-Type: application/json

{
  "client_id": "sa_prod_myapp_a1b2c3d4",
  "client_secret": "secret_XyZ123...ABC789"
}
```

#### Response (Success)
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 1800,
  "issued_at": "2025-01-15T10:00:00Z"
}
```

#### JWT Claims
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "client_id": "sa_prod_myapp_a1b2c3d4",
  "name": "MyApp Production Client",
  "role": "USER",
  "rate_limit": 100,
  "type": "access",
  "iat": 1705312800,
  "exp": 1705314600,
  "nbf": 1705312800
}
```

#### Error Responses

**401 Unauthorized - Invalid Credentials**
```json
{
  "error": "invalid_client",
  "error_description": "Invalid client_id or client_secret"
}
```

**403 Forbidden - Account Suspended**
```json
{
  "error": "access_denied",
  "error_description": "Service Account is suspended. Contact administrator."
}
```

**429 Too Many Requests - Rate Limit Exceeded**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{
  "error": "rate_limit_exceeded",
  "error_description": "Rate limit of 100 requests per minute exceeded",
  "retry_after": 60
}
```

---

## Breaking Changes Summary

### Removed Endpoints (Week 11+)
- ❌ `POST /api/auth/login` - Use `POST /api/auth/token` instead
- ❌ `GET /api/users/me` - Service Accounts don't have user profiles
- ❌ `PUT /api/users/{id}/password` - Service Accounts use client_secret rotation

### Changed Endpoints
- ✅ `POST /api/auth/refresh` - **No changes**, works identically

### New Endpoints
- ✅ `POST /api/service-accounts` - Create Service Account (admin only)
- ✅ `GET /api/service-accounts/{id}` - Get Service Account details
- ✅ `POST /api/service-accounts/{id}/rotate-secret` - Manual secret rotation

### JWT Claims Changes

| Claim | Old Value | New Value |
|-------|-----------|-----------|
| `sub` | `user_id` (integer) | `service_account_id` (UUID) |
| `username` | `"john.doe"` | **REMOVED** |
| `email` | `"john.doe@company.com"` | **REMOVED** |
| `ldap_groups` | `["cn=Users,ou=Groups"]` | **REMOVED** |
| `client_id` | **NEW** | `"sa_prod_myapp_a1b2c3d4"` |
| `name` | **NEW** | `"MyApp Production Client"` |
| `rate_limit` | **NEW** | `100` (requests/min) |

---

## Security Best Practices

### 1. Credential Storage
**❌ НЕ ДЕЛАЙТЕ**:
```python
# Hardcoded credentials in code
client_id = "sa_prod_myapp_a1b2c3d4"
client_secret = "secret_XyZ123...ABC789"  # ❌ NEVER DO THIS
```

**✅ ПРАВИЛЬНО**:
```python
# Environment variables
import os
client_id = os.getenv("ARTSTORE_CLIENT_ID")
client_secret = os.getenv("ARTSTORE_CLIENT_SECRET")
```

**✅ ЛУЧШЕ**:
```python
# Secrets management service (AWS Secrets Manager, Vault)
import boto3

secrets = boto3.client('secretsmanager')
response = secrets.get_secret_value(SecretId='artstore/credentials')
credentials = json.loads(response['SecretString'])

client_id = credentials['client_id']
client_secret = credentials['client_secret']
```

### 2. Client Secret Rotation
- Автоматическая ротация каждые 90 дней
- Уведомление за 7 дней до истечения срока
- Dual secret period: старый + новый secret активны 24 часа

**Ротация без downtime**:
```python
# 1. Request new secret (старый остается активным 24h)
response = requests.post(
    f"{base_url}/api/service-accounts/{account_id}/rotate-secret",
    headers={"Authorization": f"Bearer {admin_token}"}
)
new_secret = response.json()["new_client_secret"]

# 2. Update secret in your secrets manager
update_secret_in_vault(new_secret)

# 3. Deploy updated configuration (graceful rollout)
deploy_application_update()

# 4. Old secret automatically expires after 24 hours
```

### 3. Rate Limiting Handling
```python
import time

def make_request_with_retry(client, method, endpoint, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.request(method, endpoint)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                print(f"Rate limit exceeded. Waiting {retry_after}s...")
                time.sleep(retry_after)
            else:
                raise

    raise Exception(f"Failed after {max_retries} retries")
```

### 4. Token Caching
```python
# Cache tokens to avoid unnecessary auth requests
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379)

def get_cached_token(client_id):
    cached = redis_client.get(f"artstore:token:{client_id}")
    if cached:
        token_data = json.loads(cached)
        # Check if token is still valid (with 5min buffer)
        if token_data["expires_at"] > time.time() + 300:
            return token_data["access_token"]
    return None

def cache_token(client_id, access_token, expires_in):
    token_data = {
        "access_token": access_token,
        "expires_at": time.time() + expires_in
    }
    # Cache with TTL = expires_in
    redis_client.setex(
        f"artstore:token:{client_id}",
        expires_in,
        json.dumps(token_data)
    )
```

---

## Testing and Validation

### Test Environment
Migration testing доступен в test environment:
- **URL**: `https://artstore-test.example.com`
- **Test Service Account**: Contact admin for test credentials

### Validation Checklist

- [ ] Service Account credentials получены от администратора
- [ ] Credentials сохранены в защищенном secrets storage
- [ ] Код обновлен для использования `/api/auth/token`
- [ ] Token refresh logic корректно обрабатывает новые claims
- [ ] Error handling обновлен для новых error codes
- [ ] Rate limiting корректно обрабатывается
- [ ] Integration tests passed в test environment
- [ ] Production deployment plan готов
- [ ] Rollback plan документирован
- [ ] Monitoring и alerting настроены

### Sample Integration Test
```python
import unittest
import os

class TestArtStoreMigration(unittest.TestCase):
    def setUp(self):
        self.client = ArtStoreClient(
            base_url=os.getenv("ARTSTORE_TEST_URL"),
            client_id=os.getenv("ARTSTORE_TEST_CLIENT_ID"),
            client_secret=os.getenv("ARTSTORE_TEST_CLIENT_SECRET")
        )

    def test_authentication(self):
        """Test OAuth 2.0 authentication"""
        self.client.authenticate()
        self.assertIsNotNone(self.client.access_token)
        self.assertIsNotNone(self.client.refresh_token)

    def test_token_refresh(self):
        """Test token refresh flow"""
        self.client.authenticate()
        old_token = self.client.access_token

        # Force token expiration
        self.client.token_expires_at = datetime.now()

        # Make request (should auto-refresh)
        response = self.client.request("GET", "/api/health/ready")
        self.assertEqual(response.status_code, 200)

        # Verify token was refreshed
        self.assertNotEqual(old_token, self.client.access_token)

    def test_file_search(self):
        """Test file search with new authentication"""
        response = self.client.request("GET", "/api/files/search",
                                       params={"query": "test"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_rate_limiting(self):
        """Test rate limiting handling"""
        # Make requests until rate limit hit
        with self.assertRaises(requests.exceptions.HTTPError) as cm:
            for i in range(150):  # Exceed 100 req/min limit
                self.client.request("GET", "/api/health/ready")

        self.assertEqual(cm.exception.response.status_code, 429)

if __name__ == '__main__':
    unittest.main()
```

---

## FAQ

### Q: Когда будет отключен старый метод аутентификации?
**A**: Week 11 (2025-02-12). После этой даты endpoint `/api/auth/login` будет удален.

### Q: Нужно ли менять токены refresh?
**A**: Нет, refresh token flow остается неизменным. Используйте тот же endpoint `/api/auth/refresh`.

### Q: Как получить Service Account для моего приложения?
**A**: Обратитесь к администратору ArtStore. Предоставьте: название приложения, требуемую роль (USER/ADMIN), ожидаемый RPS.

### Q: Что делать если client_secret скомпрометирован?
**A**: Немедленно свяжитесь с администратором для ротации secret через endpoint `/api/service-accounts/{id}/rotate-secret`.

### Q: Поддерживается ли migration path для существующих токенов?
**A**: Нет. Все токены, выданные через `/api/auth/login`, станут недействительными после Week 11. Вам нужно получить новые токены через `/api/auth/token`.

### Q: Изменились ли permissions и RBAC?
**A**: Нет, ролевая модель (ADMIN, USER, AUDITOR, READONLY) осталась прежней. Только механизм аутентификации изменился.

### Q: Как тестировать миграцию без влияния на production?
**A**: Используйте test environment `https://artstore-test.example.com`. Запросите test Service Account у администратора.

### Q: Поддерживаются ли multiple Service Accounts для одного приложения?
**A**: Да, вы можете иметь разные Service Accounts для production, staging, development окружений.

### Q: Что происходит при rate limit превышении?
**A**: API вернет `429 Too Many Requests` с `Retry-After` header. Ваше приложение должно корректно обработать это и подождать указанное время.

### Q: Будут ли изменения в API endpoints кроме аутентификации?
**A**: Нет, все file management endpoints (`/api/files/*`) остаются неизменными. Только authentication flow меняется.

---

## Support Channels

### Migration Support
- **Slack**: `#artstore-migration`
- **Email**: `artstore-support@example.com`
- **Документация**: https://docs.artstore.example.com/migration
- **Issue Tracker**: https://issues.artstore.example.com/MIGRATION

### Emergency Contacts
- **On-call Engineer**: +1-555-ARTSTORE (24/7 during migration period)
- **Admin Team Lead**: admin-lead@example.com

### Office Hours (Weeks 7-10)
- **Monday-Friday**: 9:00-17:00 UTC
- **Migration Q&A Sessions**: Tuesdays 14:00 UTC (Zoom link in Slack)

---

## Appendix A: Environment Variable Template

```bash
# .env.example - ArtStore Service Account Configuration

# Service Account Credentials (REQUIRED)
ARTSTORE_CLIENT_ID=sa_prod_myapp_a1b2c3d4
ARTSTORE_CLIENT_SECRET=secret_XyZ123...ABC789

# ArtStore API Configuration
ARTSTORE_BASE_URL=https://artstore.example.com
ARTSTORE_TIMEOUT=10  # seconds

# Rate Limiting (optional, for client-side throttling)
ARTSTORE_RATE_LIMIT=100  # requests per minute
ARTSTORE_BURST_LIMIT=10  # burst allowance

# Token Caching (optional)
ARTSTORE_CACHE_ENABLED=true
ARTSTORE_CACHE_REDIS_URL=redis://localhost:6379/0

# Retry Configuration (optional)
ARTSTORE_MAX_RETRIES=3
ARTSTORE_RETRY_BACKOFF=exponential  # linear|exponential
```

---

## Appendix B: Monitoring and Alerting

### Recommended Metrics

```yaml
# Prometheus metrics to monitor
artstore_auth_requests_total:
  type: counter
  labels: [method, status]
  description: Total authentication requests by method (login vs token)

artstore_auth_latency_seconds:
  type: histogram
  labels: [method]
  description: Authentication latency distribution

artstore_token_refresh_total:
  type: counter
  labels: [status]
  description: Token refresh attempts

artstore_rate_limit_exceeded_total:
  type: counter
  description: Number of rate limit violations
```

### Recommended Alerts

```yaml
# Alert when using deprecated endpoint
- alert: DeprecatedAuthMethodUsage
  expr: rate(artstore_auth_requests_total{method="login"}[5m]) > 0
  for: 1h
  annotations:
    summary: "Application still using deprecated /api/auth/login"
    description: "Migrate to /api/auth/token before Week 11"

# Alert on high rate of auth failures
- alert: HighAuthFailureRate
  expr: rate(artstore_auth_requests_total{status="401"}[5m]) > 0.1
  for: 5m
  annotations:
    summary: "High authentication failure rate"
    description: "Check client_secret validity"

# Alert on rate limiting
- alert: RateLimitExceeded
  expr: increase(artstore_rate_limit_exceeded_total[1h]) > 10
  annotations:
    summary: "Rate limit frequently exceeded"
    description: "Consider requesting higher rate limit or optimizing request patterns"
```

---

**Документ версия**: 1.0
**Последнее обновление**: 2025-01-12
**Следующий review**: 2025-02-01 (Week 10 - Pre-cleanup verification)
