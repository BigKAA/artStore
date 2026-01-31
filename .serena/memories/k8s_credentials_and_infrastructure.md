# K8s ArtStore — Credentials & Infrastructure

## Инфраструктура кластера

### PostgreSQL
- **Namespace:** `pg`
- **Service:** `postgresql.pg.svc:5432`, NodePort `32543`
- **Суперпользователь PostgreSQL:** `postgres` / `qjkMzdJh68`
- **Суперпользователь (owner):** `artur` / `password`
- **Пользователь ArtStore:** `artstore` / `password`
- **Базы данных:** `artstore`, `artstore_admin`, `artstore_query`
- **pgAdmin:** `pg.kryukov.lan`
- **Инициализация:** `k8s/scripts/init-postgres.sql`

### Redis
- **Namespace:** `redis`
- **Service:** `redis-master.redis.svc:6379`
- **Password:** `qUwTt8g9it`

### MinIO (namespace artstore)
- **Service:** `minio:9000` (API), `minio:9001` (Console)
- **Root User:** `minioadmin`
- **Root Password:** `minioadmin`
- **Bucket:** `artstore-files`
- **Console через Gateway:** `http://minio.kryukov.lan`

### Harbor (Container Registry)
- **URL:** `https://harbor.kryukov.lan`
- **Credentials:** `admin` / `password`
- **Проект:** `library` (публичный)
- **Образы:** `harbor.kryukov.lan/library/<module>:latest`

### Gateway
- **Hostname:** `artstore.kryukov.lan`
- **GatewayClass:** `eg` (Envoy Gateway)
- **MetalLB:** IP pool `192.168.218.180-190`

## Credentials приложения ArtStore

### Service Account (для service-to-service auth)
- **Client ID:** `sa_prod_admin_service_db0fd1af`
- **Client Secret:** `Test-Password123`
- **Role:** ADMIN
- **Используется:** ingester-module, query-module, storage-element для вызовов admin-module API

### Admin User (для Admin UI и SUPER_ADMIN операций)
- **Username:** `admin`
- **Password:** `Admin123!` (сброшен вручную 2026-01-31)
- **Email:** `admin@artstore.local`
- **Role:** `super_admin`
- **Endpoint:** `POST /api/v1/admin-auth/login`

## Получение токенов

### Admin User токен (SUPER_ADMIN, нужен для регистрации SE и управления)
```bash
# Через port-forward
kubectl port-forward -n artstore svc/admin-module 8000:8000

# Записать тело запроса в файл (избегает проблем с escape в zsh)
# Файл login.json: {"username":"admin","password":"Admin123!"}

curl -s -X POST http://localhost:8000/api/v1/admin-auth/login \
  -H 'Content-Type: application/json' \
  -d @login.json

# Или через Gateway:
curl -s -X POST http://artstore.kryukov.lan/api/v1/admin-auth/login \
  -H 'Content-Type: application/json' \
  -d @login.json

# Ответ: {"access_token": "eyJ...", "refresh_token": "...", "token_type": "bearer"}
```

### Service Account токен (для API операций с файлами)
```bash
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"sa_prod_admin_service_db0fd1af","client_secret":"Test-Password123"}'

# Ответ: {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 1800}
```

### Использование токена
```bash
TOKEN="eyJ..."
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/storage-elements/
```

### Скрипт получения токена внутри pod (без escape-проблем)
```bash
kubectl exec -n artstore deployment/admin-module -- python3 -c "
import httpx, asyncio, json
async def get():
    async with httpx.AsyncClient(base_url='http://localhost:8000') as c:
        r = await c.post('/api/v1/auth/token', json={'client_id':'sa_prod_admin_service_db0fd1af','client_secret':'Test-Password123'})
        print(r.json()['access_token'])
asyncio.run(get())
"
```

## Регистрация Storage Elements

SE не самостоятельно регистрируются. Нужен SUPER_ADMIN токен (admin user).

```bash
# Получить admin токен (см. выше), затем:
curl -X POST http://localhost:8000/api/v1/storage-elements/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_url":"http://storage-element-se-01:8000","name":"SE-01"}'

# Повторить для se-02, se-03
```

## Порты модулей в K8s
| Модуль | Service | Port |
|--------|---------|------|
| admin-module | admin-module:8000 | 8000 |
| ingester-module | ingester-module:8020 | 8020 |
| query-module | query-module:8030 | 8030 |
| storage-element-se-01 | storage-element-se-01:8000 | 8000 |
| storage-element-se-02 | storage-element-se-02:8000 | 8000 |
| storage-element-se-03 | storage-element-se-03:8000 | 8000 |
| minio | minio:9000/9001 | 9000/9001 |
