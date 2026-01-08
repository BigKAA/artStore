# Sprint 15.2: File Registry Integration

## 📋 ОБЗОР

**Цель**: Полная интеграция Ingester Module ↔ Admin Module file registry для устранения потери консистентности данных.

**Статус**: ✅ API и инфраструктура реализована, требуется интеграция в upload/finalize процессы

---

## ✅ РЕАЛИЗОВАНО

### 1. Admin Module - File Registry API

**Файлы созданы**:
- ✅ `admin-module/app/schemas/file.py` - Pydantic schemas
- ✅ `admin-module/app/services/file_service.py` - Бизнес-логика
- ✅ `admin-module/app/api/v1/endpoints/files.py` - REST API endpoints
- ✅ `admin-module/app/main.py` - Router подключен

**Endpoints**:
```
POST   /api/v1/files           - Регистрация файла (Ingester → Admin)
GET    /api/v1/files/{id}      - Получение метаданных
PUT    /api/v1/files/{id}      - Обновление (финализация)
DELETE /api/v1/files/{id}      - Soft delete
GET    /api/v1/files           - Список файлов (pagination)
```

**Features**:
- OAuth 2.0 Bearer authentication
- Role-based access control (ADMIN, USER, AUDITOR, READONLY)
- Transaction safety через async SQLAlchemy
- Audit logging через middleware
- Validation с Pydantic

### 2. Ingester Module - Admin Client

**Файл обновлен**:
- ✅ `ingester-module/app/services/admin_client.py`

**Новые методы**:
```python
await admin_client.register_file(file_data)  # POST /api/v1/files
await admin_client.update_file(file_id, data)  # PUT /api/v1/files/{id}
await admin_client.get_file(file_id)  # GET /api/v1/files/{id}
```

**Features**:
- Async HTTP calls через httpx
- OAuth 2.0 token management с auto-refresh
- Retry logic для 401 errors
- Error handling и logging

---

## 🔨 ТРЕБУЕТСЯ ИНТЕГРАЦИЯ

### 1. Upload Service Integration

**Файл**: `ingester-module/app/services/upload_service.py`

**Метод**: `upload_file()` (строки 203-412)

**Изменения**:

```python
# После строки 349 (после успешной загрузки в SE)
# ДОБАВИТЬ регистрацию файла в Admin Module

from app.services.admin_client import get_admin_client, AdminClientError

# В конце метода upload_file(), перед return UploadResponse:

# Sprint 15.2: Регистрация файла в Admin Module file registry
try:
    admin_client = await get_admin_client()

    # Подготовка данных для регистрации
    file_register_data = {
        "file_id": str(result['file_id']),
        "original_filename": file.filename or "unknown",
        "storage_filename": result.get('storage_filename', result['file_id']),
        "file_size": file_size,
        "checksum_sha256": result.get('checksum', checksum),
        "content_type": file.content_type,
        "description": request.description,
        "retention_policy": request.retention_policy.value,
        "ttl_expires_at": ttl_expires_at.isoformat() if ttl_expires_at else None,
        "ttl_days": request.ttl_days,
        "storage_element_id": storage_element_id,
        "storage_path": f"/files/{result['file_id']}",
        "compressed": request.compress,
        "compression_algorithm": request.compression_algorithm.value if request.compress else None,
        "original_size": file_size if request.compress else None,
        "uploaded_by": user_id,
        "upload_source_ip": None,  # TODO: extract from request
        "user_metadata": request.metadata,
    }

    # Регистрация в file registry
    registry_result = await admin_client.register_file(file_register_data)

    logger.info(
        "File registered in Admin Module registry",
        extra={
            "file_id": str(result['file_id']),
            "registry_file_id": registry_result.get('file_id'),
        }
    )

except AdminClientError as e:
    # NON-CRITICAL: Файл загружен в SE, но не зарегистрирован в Admin Module
    # Может быть зарегистрирован позже через reconciliation job
    logger.error(
        "Failed to register file in Admin Module registry",
        extra={
            "file_id": str(result['file_id']),
            "error": str(e),
            "user_id": user_id
        }
    )
    # Не прерываем операцию - файл уже в SE
    # TODO Sprint 15.3: Implement reconciliation job для retry

return UploadResponse(...)  # Existing return
```

**Важные моменты**:
1. Регистрация в Admin Module происходит ПОСЛЕ успешной загрузки в Storage Element
2. Ошибка регистрации НЕ прерывает upload (файл уже в SE)
3. Требуется reconciliation job для retry failed registrations

### 2. Finalize Service Integration

**Файл**: `ingester-module/app/services/finalize_service.py`

**Метод**: `finalize_file()` (строки 141-326)

**Изменения**:

```python
# После строки 253 (после успешной верификации checksum)
# ДОБАВИТЬ обновление файла в Admin Module

from app.services.admin_client import get_admin_client, AdminClientError

# В Phase 4: Success (строка 248-283)
# ПЕРЕД установкой status = COMPLETED, ДОБАВИТЬ:

# Sprint 15.2: Обновление файла в Admin Module (финализация)
try:
    admin_client = await get_admin_client()

    # Подготовка данных для обновления
    file_update_data = {
        "retention_policy": "permanent",  # temporary → permanent
        "storage_element_id": target_se_id,
        "storage_path": f"/files/{file_id}",
        "finalized_at": completed_at.isoformat(),
    }

    # Обновление в file registry
    registry_result = await admin_client.update_file(str(file_id), file_update_data)

    logger.info(
        "File updated in Admin Module registry (finalized)",
        extra={
            "file_id": str(file_id),
            "retention_policy": "permanent",
            "storage_element_id": target_se_id,
        }
    )

except AdminClientError as e:
    # CRITICAL: Финализация частично выполнена
    # Файл скопирован в target SE, но registry не обновлен
    logger.error(
        "Failed to update file in Admin Module registry",
        extra={
            "file_id": str(file_id),
            "error": str(e),
            "transaction_id": str(transaction_id)
        }
    )

    # TODO Sprint 15.3: Добавить в reconciliation queue
    # Пока продолжаем - финализация технически успешна
    # Registry будет обновлен через reconciliation job
```

**Важные моменты**:
1. Обновление registry происходит ПОСЛЕ верификации checksum
2. Если обновление failed - финализация считается успешной (файл скопирован)
3. Requires reconciliation job для consistency

### 3. Finalize Endpoint Integration

**Файл**: `ingester-module/app/api/v1/endpoints/finalize.py`

**Метод**: `finalize_file()` (строки 87-226)

**Изменения**:

```python
# ЗАМЕНИТЬ MVP placeholder (строки 124-175) на:

# Sprint 15.2: Получение информации о файле из Admin Module file registry
try:
    from app.services.admin_client import get_admin_client, AdminClientError

    admin_client = await get_admin_client()

    # Получить метаданные файла из registry
    file_metadata = await admin_client.get_file(str(file_id))

    if not file_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found in registry"
        )

    # Валидация: файл должен быть temporary
    if file_metadata.get("retention_policy") != "temporary":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File {file_id} is not temporary (retention_policy={file_metadata.get('retention_policy')})"
        )

    # Валидация: файл не должен быть уже финализирован
    if file_metadata.get("finalized_at"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File {file_id} is already finalized"
        )

    # Извлечение данных из registry
    source_se_id = file_metadata.get("storage_element_id")
    source_se_endpoint = None  # Получить из StorageSelector
    file_size = file_metadata.get("file_size")
    checksum = file_metadata.get("checksum_sha256")

    # Получить endpoint для source SE через StorageSelector
    from app.services.storage_selector import get_storage_selector

    storage_selector = await get_storage_selector()
    if not storage_selector._initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="StorageSelector not initialized"
        )

    # Найти source SE endpoint
    se_endpoints = storage_selector._endpoints
    if source_se_id not in se_endpoints:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Source SE {source_se_id} not available"
        )

    source_se_endpoint = se_endpoints[source_se_id]

    logger.info(
        "File metadata retrieved from registry",
        extra={
            "file_id": str(file_id),
            "source_se_id": source_se_id,
            "file_size": file_size,
            "retention_policy": file_metadata.get("retention_policy")
        }
    )

except AdminClientError as e:
    logger.error(
        "Failed to get file metadata from Admin Module",
        extra={
            "file_id": str(file_id),
            "error": str(e)
        }
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Failed to retrieve file metadata: {str(e)}"
    )
```

---

## 📊 DATABASE MIGRATION

**Файл**: `admin-module/alembic/versions/xxx_add_file_registry.py`

**Требуется создать migration для**:
- Таблица `files` (уже определена в models/file.py)
- Indexes для оптимизации query:
  - `idx_files_retention_policy`
  - `idx_files_storage_element_id`
  - `idx_files_ttl_expires_at`
  - `idx_files_deleted_at`
  - `idx_files_created_at`

**Команды**:
```bash
cd admin-module

# Генерация migration
alembic revision --autogenerate -m "Add file registry tables"

# Применение migration
alembic upgrade head
```

---

## 🧪 ТЕСТИРОВАНИЕ

### Unit Tests

**Admin Module**:
```bash
cd admin-module
pytest tests/test_file_service.py -v
pytest tests/test_file_endpoints.py -v
```

**Ingester Module**:
```bash
cd ingester-module
pytest tests/test_upload_with_registry.py -v
pytest tests/test_finalize_with_registry.py -v
```

### Integration Tests

**End-to-End Workflow**:
1. Upload temporary file → проверить registry
2. Finalize file → проверить обновление registry
3. Query file → проверить метаданные
4. Delete file → проверить soft delete

**Test Script**:
```bash
#!/bin/bash
# integration_test.sh

# 1. Получить токен
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"...","client_secret":"..."}' \
  | jq -r '.access_token')

# 2. Upload file
FILE_ID=$(curl -s -X POST http://localhost:8020/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.pdf" \
  -F "retention_policy=temporary" \
  | jq -r '.file_id')

echo "Uploaded file_id: $FILE_ID"

# 3. Check file in registry
curl -s -X GET "http://localhost:8000/api/v1/files/$FILE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 4. Finalize file
curl -s -X POST "http://localhost:8020/api/v1/files/finalize/$FILE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 5. Check updated registry
curl -s -X GET "http://localhost:8000/api/v1/files/$FILE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 🔧 DEPLOYMENT CHECKLIST

- [ ] Apply database migration (`alembic upgrade head`)
- [ ] Restart Admin Module (`docker-compose restart artstore_admin_module`)
- [ ] Restart Ingester Module (`docker-compose restart artstore_ingester_module`)
- [ ] Verify `/docs` Swagger - новый `/api/v1/files` раздел
- [ ] Run integration tests
- [ ] Check logs для file registration успешности
- [ ] Monitor metrics: `admin_module_file_registry_*`

---

## 📈 METRICS & MONITORING

**Prometheus Metrics** (добавить в Admin Module):
```python
from prometheus_client import Counter, Histogram

# File registry операции
file_registry_operations = Counter(
    "admin_module_file_registry_operations_total",
    "File registry operations",
    ["operation", "status"]  # operation: register, update, delete
)

file_registry_duration = Histogram(
    "admin_module_file_registry_duration_seconds",
    "File registry operation duration",
    ["operation"]
)
```

**Grafana Dashboard**:
- File registration rate (per minute)
- Failed registrations count
- Average registration latency
- Pending reconciliation queue size

---

## 🐛 TROUBLESHOOTING

### Problem: File uploaded but not registered

**Симптомы**:
- Файл существует в Storage Element
- `GET /api/v1/files/{id}` возвращает 404

**Причины**:
1. Admin Module был недоступен при upload
2. Network timeout при регистрации
3. Authentication failed (invalid token)

**Решение**:
1. Check Admin Module health: `curl http://localhost:8000/health/ready`
2. Check Ingester logs: `docker-compose logs -f artstore_ingester_module`
3. Manual registration через Admin API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/files \
     -H "Authorization: Bearer $TOKEN" \
     -d @file_data.json
   ```

### Problem: Finalize completed but registry not updated

**Симптомы**:
- Файл скопирован в RW SE
- `GET /api/v1/files/{id}` показывает `retention_policy=temporary`

**Причины**:
1. Admin Module недоступен при finalize
2. Update failed из-за validation error

**Решение**:
1. Check Finalize Service logs
2. Manual update через Admin API:
   ```bash
   curl -X PUT "http://localhost:8000/api/v1/files/$FILE_ID" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"retention_policy":"permanent","storage_element_id":"rw-se-01","finalized_at":"..."}'
   ```

---

## 🚀 NEXT STEPS (Sprint 15.3)

1. **Reconciliation Job**: Background процесс для retry failed registrations
2. **Bulk Registration**: API для batch регистрации файлов
3. **Audit Trail**: Полный audit log изменений файлов
4. **Query Module Integration**: Использование file registry для search
5. **File Cleanup**: Integration с Garbage Collector для physical deletion

---

## 📚 REFERENCES

- **File Model**: `admin-module/app/models/file.py`
- **Retention Policy**: `temporary` (Edit SE, TTL) vs `permanent` (RW SE, долгосрочное)
- **Two-Phase Commit**: Finalize process документация
- **Service Discovery**: Storage Element selection через Redis/Admin Module

---

**Дата**: 2026-01-08
**Автор**: Claude Code (Sprint 15.2 Implementation)
**Статус**: ✅ Реализовано (требуется интеграция в upload/finalize)
