# Docker Compose Module Requirements

**Дата**: 2025-11-14
**Статус**: ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ

## Правило разделения Docker Compose файлов

### Корневой docker-compose.yml
**Расположение**: `/home/artur/Projects/artStore/docker-compose.yml`

**Назначение**: Запуск ТОЛЬКО инфраструктурных сервисов, общих для всех модулей

**Сервисы**:
- `postgres` - PostgreSQL database
- `pgadmin` - PostgreSQL admin interface
- `redis` - Redis cache/pub-sub
- `minio` - S3-compatible object storage
- `ldap` - LDAP directory server (389ds)
- `dex` - OpenID Connect provider
- `nginx` - Reverse proxy / load balancer

**Network**: `artstore_network` (bridge, shared across all modules)

### Module docker-compose.yml
**Расположение**: `/home/artur/Projects/artStore/{module-name}/docker-compose.yml`

**Назначение**: Запуск ТОЛЬКО конкретного модуля приложения

**Правила**:
1. ❌ **НЕ запускать** инфраструктурные сервисы (postgres, redis, minio, ldap, dex, nginx)
2. ✅ **Запускать ТОЛЬКО** сервис самого модуля
3. ✅ **Использовать external network** `artstore_network` для связи с инфраструктурой
4. ✅ **Зависимости через depends_on** указывать ТОЛЬКО если сервис в том же docker-compose.yml
5. ✅ **Environment variables** для подключения к инфраструктурным сервисам

### Примеры модулей

#### Admin Module docker-compose.yml
```yaml
services:
  admin-module:
    build: .
    container_name: artstore_admin
    ports:
      - "8000:8000"
    environment:
      - DATABASE_HOST=postgres  # Использует postgres из корневого docker-compose.yml
      - REDIS_HOST=redis        # Использует redis из корневого docker-compose.yml
    networks:
      - artstore_network

networks:
  artstore_network:
    external: true
    name: artstore_network
```

#### Storage Element docker-compose.yml
```yaml
services:
  storage-element:
    build: .
    container_name: artstore_storage_element
    ports:
      - "8010:8010"
    environment:
      - DATABASE_HOST=postgres  # Использует postgres из корневого docker-compose.yml
      - REDIS_HOST=redis        # Использует redis из корневого docker-compose.yml
      - MINIO_ENDPOINT=minio:9000  # Использует minio из корневого docker-compose.yml
    networks:
      - artstore_network

networks:
  artstore_network:
    external: true
    name: artstore_network
```

#### Ingester Module docker-compose.yml (ПРАВИЛЬНЫЙ)
```yaml
services:
  ingester-module:
    build: .
    container_name: artstore_ingester
    ports:
      - "8020:8020"
    environment:
      - STORAGE_ELEMENT_BASE_URL=http://storage-element:8010
      - REDIS_HOST=redis        # Использует redis из корневого docker-compose.yml
    volumes:
      - ../admin-module/keys:/app/keys:ro
    networks:
      - artstore_network

networks:
  artstore_network:
    external: true
    name: artstore_network
```

## Workflow запуска

### 1. Запуск инфраструктуры (ОДИН РАЗ)
```bash
cd /home/artur/Projects/artStore
docker-compose up -d
```

Результат: Запущены postgres, redis, minio, ldap, dex, nginx

### 2. Запуск модулей (ОТДЕЛЬНО для каждого)
```bash
# Admin Module
cd /home/artur/Projects/artStore/admin-module
docker-compose up -d

# Storage Element
cd /home/artur/Projects/artStore/storage-element
docker-compose up -d

# Ingester Module
cd /home/artur/Projects/artStore/ingester-module
docker-compose up -d

# Query Module
cd /home/artur/Projects/artStore/query-module
docker-compose up -d
```

### 3. Остановка
```bash
# Остановка конкретного модуля
cd /home/artur/Projects/artStore/{module-name}
docker-compose down

# Остановка инфраструктуры (ВНИМАНИЕ: остановит ВСЕ модули)
cd /home/artur/Projects/artStore
docker-compose down
```

## Преимущества такой архитектуры

1. **Разделение ответственности**: Инфраструктура отделена от модулей приложения
2. **Независимое развертывание**: Каждый модуль можно запускать/останавливать отдельно
3. **Общая сеть**: Все модули видят друг друга через `artstore_network`
4. **Единая инфраструктура**: PostgreSQL, Redis, MinIO запускаются один раз для всех модулей
5. **Удобная разработка**: Можно работать только с одним модулем, не поднимая все остальные

## Ошибки, которых нужно избегать

❌ **НЕПРАВИЛЬНО**: Запускать redis в docker-compose.yml модуля
```yaml
# ingester-module/docker-compose.yml (ПЛОХО!)
services:
  ingester-module:
    build: .
  redis:  # ❌ НЕ НУЖНО! Redis должен быть в корневом docker-compose.yml
    image: redis:7-alpine
```

✅ **ПРАВИЛЬНО**: Использовать redis из корневого docker-compose.yml
```yaml
# ingester-module/docker-compose.yml (ХОРОШО!)
services:
  ingester-module:
    build: .
    environment:
      - REDIS_HOST=redis  # ✅ Используем redis из корневого docker-compose.yml
    networks:
      - artstore_network

networks:
  artstore_network:
    external: true  # ✅ Подключаемся к существующей сети
```

## Compliance Checklist

При создании нового модуля проверяй:
- [ ] docker-compose.yml содержит ТОЛЬКО сервис модуля
- [ ] НЕ содержит postgres, redis, minio, ldap, dex, nginx
- [ ] Использует `networks.artstore_network.external: true`
- [ ] Environment variables указывают на инфраструктурные сервисы (redis, postgres, minio)
- [ ] depends_on НЕ указывает на сервисы из корневого docker-compose.yml
- [ ] Ports не конфликтуют с другими модулями

## Обновление существующих модулей

Если модуль содержит инфраструктурные сервисы - УДАЛИТЬ их и использовать корневой docker-compose.yml.

**Пример**: Ingester Module содержал redis - нужно удалить сервис redis и использовать `REDIS_HOST=redis` из корневого docker-compose.yml.
