# ArtStore Deployment Guide

## JWT Key Management

### Key File Permissions

**CRITICAL**: JWT ключи требуют правильных permissions для корректной работы в Docker контейнерах.

#### Required Permissions

```bash
# Public key (читается всеми модулями)
chmod 644 /path/to/public_key.pem

# Private key (читается только Admin Module)
chmod 600 /path/to/private_key.pem  # для production
chmod 644 /path/to/private_key.pem  # для development в Docker
```

#### Admin Module Keys

**Локация**: `/home/artur/Projects/artStore/admin-module/.keys/`

```bash
cd /home/artur/Projects/artStore/admin-module/.keys/
chmod 644 private_key.pem public_key.pem
```

**Docker Mount**: `-v /path/to/admin-module/.keys:/app/.keys:ro`

**Environment Variables**:
```env
JWT_PRIVATE_KEY_PATH=/app/.keys/private_key.pem
JWT_PUBLIC_KEY_PATH=/app/.keys/public_key.pem
JWT_ALGORITHM=RS256
```

#### Query Module Keys

**Локация**: `/home/artur/Projects/artStore/query-module/keys/`

```bash
cd /home/artur/Projects/artStore/query-module/keys/
chmod 644 public_key.pem
```

**Docker Mount**: `-v /path/to/query-module/keys:/app/keys:ro`

**Environment Variables**:
```env
JWT_PUBLIC_KEY_PATH=/app/keys/public_key.pem
JWT_ALGORITHM=RS256
```

#### Ingester Module Keys

**Локация**: `/home/artur/Projects/artStore/ingester-module/keys/`

```bash
cd /home/artur/Projects/artStore/ingester-module/keys/
chmod 644 public_key.pem
```

**Docker Mount**: `-v /path/to/ingester-module/keys:/app/keys:ro`

**Environment Variables**:
```env
JWT_PUBLIC_KEY_PATH=/app/keys/public_key.pem
JWT_ALGORITHM=RS256
```

### Key Rotation (Auto-implemented)

Admin Module автоматически ротирует JWT ключи каждые 24 часа:
- Scheduler job запускается при старте Admin Module
- Новые ключи генерируются и сохраняются
- Старые ключи сохраняются с timestamp для graceful transition
- Все подключенные модули автоматически обновляют публичный ключ

## Database Migrations

### Query Module Alembic

После исправления (Sprint 20) alembic.ini теперь включен в Docker образ.

#### Запуск миграций внутри контейнера

```bash
# Проверить текущую версию
docker exec artstore_query_module alembic current

# Применить миграции
docker exec artstore_query_module alembic upgrade head

# Посмотреть историю
docker exec artstore_query_module alembic history
```

#### Запуск миграций при развертывании

```bash
# В docker-compose.yml добавить init container
services:
  query-module-migration:
    image: artstore_query_module:latest
    command: alembic upgrade head
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql+asyncpg://artstore:password@postgres:5432/artstore
    restart: "no"

  query-module:
    image: artstore_query_module:latest
    depends_on:
      query-module-migration:
        condition: service_completed_successfully
```

### Admin Module Alembic

```bash
# Admin Module использует автоматическую миграцию при старте
# Или ручное выполнение через venv:
cd /home/artur/Projects/artStore/admin-module
source /home/artur/Projects/artStore/.venv/bin/activate
DATABASE_URL="postgresql+asyncpg://artstore:password@localhost:5432/artstore_admin" \
  JWT_PRIVATE_KEY_PATH="/path/to/admin-module/.keys/private_key.pem" \
  JWT_PUBLIC_KEY_PATH="/path/to/admin-module/.keys/public_key.pem" \
  alembic upgrade head
```

## Docker Compose Configuration

### Полная конфигурация для production

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: artstore
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: artstore
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U artstore"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  admin-module:
    image: admin-module_admin-module:latest
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"
    volumes:
      - ./admin-module/.data:/app/.data
      - ./admin-module/.keys:/app/.keys:ro
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_USERNAME: artstore
      DB_PASSWORD: ${DB_PASSWORD}
      DB_DATABASE: artstore_admin
      REDIS_HOST: redis
      REDIS_PORT: 6379
      JWT_PRIVATE_KEY_PATH: /app/.keys/private_key.pem
      JWT_PUBLIC_KEY_PATH: /app/.keys/public_key.pem
      JWT_ALGORITHM: RS256
      LOG_LEVEL: INFO
      LOG_FORMAT: json

  query-module:
    image: artstore_query_module:latest
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8030:8030"
    volumes:
      - ./query-module/keys:/app/keys:ro
    environment:
      DATABASE_URL: postgresql+asyncpg://artstore:${DB_PASSWORD}@postgres:5432/artstore
      REDIS_URL: redis://redis:6379/0
      JWT_PUBLIC_KEY_PATH: /app/keys/public_key.pem
      JWT_ALGORITHM: RS256
      LOG_LEVEL: INFO
      LOG_FORMAT: json

volumes:
  postgres_data:
```

## Troubleshooting

### JWT Verification Errors

**Симптом**: `PermissionError: [Errno 13] Permission denied: '/app/.keys/private_key.pem'`

**Решение**:
```bash
chmod 644 /path/to/admin-module/.keys/*.pem
docker restart artstore_admin_module
```

### Missing Database Tables

**Симптом**: `relation "file_metadata_cache" does not exist`

**Решение**:
```bash
# Запустить миграции
docker exec artstore_query_module alembic upgrade head

# Или создать таблицы напрямую (см. scripts/init_query_db.sql)
```

### CORS Errors in Admin UI

**Симптом**: `Access to XMLHttpRequest blocked by CORS policy`

**Решение**: Проверить CORS настройки в backend модулях:
```python
# app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],  # Admin UI origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 307 Redirect Issues

**Симптом**: POST requests fail with 307 Temporary Redirect

**Решение**: Добавить trailing slash к URL endpoints:
```typescript
// Angular service
return this.http.post<T>(`${this.apiUrl}/`, data);  // WITH trailing slash
```

## Security Checklist

- [ ] JWT private key имеет permissions 600 (production) или 644 (development в Docker)
- [ ] JWT public key имеет permissions 644
- [ ] Все passwords в environment variables (не в коде)
- [ ] CORS настроен только на разрешенные origins
- [ ] Database credentials защищены
- [ ] Health check endpoints доступны без authentication
- [ ] Логирование в JSON формате для production
- [ ] TLS 1.3 включен для inter-service communication (будет в Sprint 21)
