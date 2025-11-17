# Настройка Тестовой Конфигурации ArtStore

## Обзор

Для тестирования системы настроены **два экземпляра Storage Element**:

1. **Storage Element 01** - Локальное файловое хранилище (порт 8010)
2. **Storage Element 02** - S3 хранилище через MinIO (порт 8011)

Оба элемента работают в режиме **edit** (полный CRUD доступ).

---

## Storage Element 01 - Локальная Файловая Система

### Характеристики
- **Тип хранилища**: Local Filesystem
- **Режим**: `edit` (полный CRUD)
- **Порт**: 8010
- **Путь хранения**: `/app/.data/storage` (внутри контейнера)
- **Docker Volume**: `artstore_storage_01_data`
- **База данных**: `artstore_storage_01`

### Конфигурация
```yaml
STORAGE_TYPE: local
STORAGE_LOCAL_BASE_PATH: /app/.data/storage
```

### Проверка
```bash
# Проверка health status
curl http://localhost:8010/health/live

# Просмотр логов
docker logs artstore_storage_element_01 -f

# Просмотр файлов в volume
docker exec -it artstore_storage_element_01 ls -la /app/.data/storage/
```

---

## Storage Element 02 - S3 Хранилище (MinIO)

### Характеристики
- **Тип хранилища**: S3 (MinIO)
- **Режим**: `edit` (полный CRUD)
- **Порт**: 8011
- **S3 Bucket**: `artstore-storage-02`
- **MinIO Endpoint**: http://minio:9000
- **База данных**: `artstore_storage_02`

### Конфигурация
```yaml
STORAGE_TYPE: s3
STORAGE_S3_ENDPOINT_URL: http://minio:9000
STORAGE_S3_ACCESS_KEY: minioadmin
STORAGE_S3_SECRET_KEY: minioadmin
STORAGE_S3_BUCKET_NAME: artstore-storage-02
STORAGE_S3_REGION: us-east-1
```

---

## Инициализация MinIO Bucket (ОБЯЗАТЕЛЬНО!)

### ⚠️ ВАЖНО
**Storage Element 02 НЕ ЗАПУСТИТСЯ без созданного bucket!**

Bucket `artstore-storage-02` должен быть создан **ВРУЧНУЮ ОДИН РАЗ** перед первым запуском Storage Element 02.

### Шаг 1: Запустите Infrastructure
```bash
docker-compose -f docker-compose.infrastructure.yml up -d
```

### Шаг 2: Дождитесь готовности MinIO
```bash
# Проверка что MinIO запущен
docker ps | grep artstore_minio

# Проверка health check
curl http://localhost:9000/minio/health/live
```

### Шаг 3: Создайте Bucket
```bash
# Войдите в контейнер MinIO
docker exec -it artstore_minio sh

# Внутри контейнера выполните:

# 1. Настройка mc alias
mc alias set local http://localhost:9000 minioadmin minioadmin

# 2. Создание bucket
mc mb local/artstore-storage-02

# 3. Установка политики доступа (private)
mc anonymous set none local/artstore-storage-02

# 4. Включение версионирования (для безопасности)
mc version enable local/artstore-storage-02

# 5. Проверка созданного bucket
mc ls local/
mc stat local/artstore-storage-02

# 6. Выход из контейнера
exit
```

### Альтернативный способ (через Web UI)
1. Откройте MinIO Console: http://localhost:9001
2. Логин: `minioadmin` / `minioadmin`
3. Перейдите в раздел **Buckets**
4. Нажмите **Create Bucket**
5. Введите имя: `artstore-storage-02`
6. Нажмите **Create**
7. Настройте Versioning в настройках bucket

---

## Запуск Системы

### Полный запуск (Infrastructure + Backend)
```bash
# 1. Запуск базовой инфраструктуры
docker-compose -f docker-compose.infrastructure.yml up -d

# 2. Создание MinIO bucket (см. выше) - ОБЯЗАТЕЛЬНО!

# 3. Запуск backend модулей
docker-compose -f docker-compose.infrastructure.yml -f docker-compose.backend.yml up -d

# 4. Проверка статуса всех сервисов
docker-compose -f docker-compose.infrastructure.yml -f docker-compose.backend.yml ps
```

### Только Infrastructure (для инициализации)
```bash
docker-compose -f docker-compose.infrastructure.yml up -d
```

### Только Backend (требует запущенную Infrastructure)
```bash
docker-compose -f docker-compose.backend.yml up -d
```

---

## Проверка Работоспособности

### 1. Проверка Health Endpoints
```bash
# Admin Module
curl http://localhost:8000/health/live

# Storage Element 01 (Local)
curl http://localhost:8010/health/live

# Storage Element 02 (S3)
curl http://localhost:8011/health/live

# Ingester Module
curl http://localhost:8020/health/live

# Query Module
curl http://localhost:8030/health/ready
```

### 2. Проверка Подключения к MinIO
```bash
# Из контейнера Storage Element 02
docker exec -it artstore_storage_element_02 sh

# Внутри контейнера (если установлен curl):
curl http://minio:9000/minio/health/live
```

### 3. Просмотр Логов
```bash
# Все сервисы
docker-compose -f docker-compose.infrastructure.yml -f docker-compose.backend.yml logs -f

# Конкретный сервис
docker logs artstore_storage_element_01 -f
docker logs artstore_storage_element_02 -f
```

---

## Тестирование Upload

### Получение JWT токена
```bash
# Аутентификация (требует созданный service account)
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "your-client-id", "client_secret": "your-client-secret"}'

# Сохраните access_token из ответа
export TOKEN="eyJ..."
```

### Upload в Storage Element 01 (Local)
```bash
curl -X POST http://localhost:8020/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.pdf" \
  -F "storage_element=storage-element-01"
```

### Upload в Storage Element 02 (S3)
```bash
curl -X POST http://localhost:8020/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.pdf" \
  -F "storage_element=storage-element-02"
```

---

## Troubleshooting

### Storage Element 02 не запускается

**Проблема**: `BucketNotFound: The bucket 'artstore-storage-02' does not exist`

**Решение**: Создайте bucket вручную (см. раздел "Инициализация MinIO Bucket")

### MinIO недоступен из контейнера

**Проблема**: `Connection refused` при подключении к MinIO

**Решение**:
```bash
# Проверьте что MinIO запущен
docker ps | grep artstore_minio

# Проверьте сеть
docker network inspect artstore_network

# Убедитесь что Storage Element 02 в той же сети
docker inspect artstore_storage_element_02 | grep artstore_network
```

### Bucket создан, но Storage Element 02 не видит файлы

**Проблема**: Bucket существует, но операции upload/download не работают

**Решение**:
```bash
# Проверьте credentials в docker-compose.backend.yml
# STORAGE_S3_ACCESS_KEY и STORAGE_S3_SECRET_KEY должны совпадать с MINIO_ROOT_USER/PASSWORD

# Проверьте политику доступа к bucket
docker exec -it artstore_minio sh
mc anonymous get local/artstore-storage-02
```

---

## Мониторинг

### Prometheus Metrics
```bash
# Admin Module
curl http://localhost:8000/metrics

# Storage Element 01
curl http://localhost:8010/metrics

# Storage Element 02
curl http://localhost:8011/metrics

# Ingester Module
curl http://localhost:8020/metrics

# Query Module
curl http://localhost:8030/metrics
```

### MinIO Web Console
- URL: http://localhost:9001
- Логин: `minioadmin` / `minioadmin`
- Просмотр buckets, metrics, logs

### PostgreSQL (PgAdmin)
- URL: http://localhost:5050
- Логин: `admin@admin.com` / `password`
- Databases:
  - `artstore_admin`
  - `artstore_storage_01`
  - `artstore_storage_02`
  - `artstore_query`

---

## Очистка Данных

### Удаление всех данных (полная переинициализация)
```bash
# Остановка всех контейнеров
docker-compose -f docker-compose.infrastructure.yml -f docker-compose.backend.yml down

# Удаление volumes
docker volume rm artstore_postgres_data
docker volume rm artstore_redis_data
docker volume rm artstore_minio_data
docker volume rm artstore_storage_01_data
docker volume rm artstore_admin_keys

# Или все volumes сразу
docker volume prune -f
```

### Удаление только данных Storage Elements
```bash
# Storage Element 01 (local)
docker volume rm artstore_storage_01_data

# Storage Element 02 (S3) - данные в MinIO
docker exec -it artstore_minio sh
mc rm --recursive --force local/artstore-storage-02
mc rb local/artstore-storage-02
```

---

## Справочная Информация

### Порты
- **8000**: Admin Module
- **8010**: Storage Element 01 (Local)
- **8011**: Storage Element 02 (S3)
- **8020**: Ingester Module
- **8030**: Query Module
- **5432**: PostgreSQL
- **6379**: Redis
- **9000**: MinIO S3 API
- **9001**: MinIO Web Console
- **5050**: PgAdmin

### Docker Volumes
- `artstore_postgres_data`: PostgreSQL данные
- `artstore_redis_data`: Redis данные
- `artstore_minio_data`: MinIO данные (включая bucket artstore-storage-02)
- `artstore_storage_01_data`: Файлы Storage Element 01
- `artstore_admin_keys`: JWT ключи (shared между модулями)

### Databases
- `artstore_admin`: Admin Module (service accounts, storage elements)
- `artstore_storage_01`: Storage Element 01 metadata cache
- `artstore_storage_02`: Storage Element 02 metadata cache
- `artstore_query`: Query Module search index

---

## Дополнительные Ресурсы

- **Скрипт инициализации**: `scripts/init-minio-buckets.sh` (справочная информация)
- **CLAUDE.md**: Полная документация по архитектуре проекта
- **docker-compose.infrastructure.yml**: Конфигурация инфраструктуры
- **docker-compose.backend.yml**: Конфигурация backend модулей
