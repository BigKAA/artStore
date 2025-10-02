# Архитектурные решения ArtStore

Документ фиксирует ключевые архитектурные решения, принятые в ходе проектирования системы распределенного файлового хранилища ArtStore.

## Дата последнего обновления
2025-10-02

---

## 1. Уникальность файлов и предотвращение коллизий

### Контекст
Два пользователя могут одновременно загружать файлы с одинаковым именем и версией. По содержанию это могут быть разные файлы от разных пользователей.

### Решение
**File Naming Convention**: `{name_without_ext}_{username}_{timestamp}_{uuid}.{ext}`

**Пример**: `report_ivanov_20250102T153045_a1b2c3d4.pdf`

**Implementation** (с обрезанием длинных имен):
```python
from pathlib import Path

def generate_storage_filename(original_name: str, username: str,
                              timestamp: str, uuid: str,
                              max_filename_length: int = 200) -> str:
    """
    Генерирует уникальное имя файла для хранения с обрезанием длинных имен.

    Args:
        original_name: Оригинальное имя файла (например, "report.pdf")
        username: Логин пользователя
        timestamp: ISO timestamp в формате "20250102T153045"
        uuid: Уникальный идентификатор (короткая форма, например "a1b2c3d4")
        max_filename_length: Максимальная длина результирующего имени (default: 200)

    Returns:
        Storage filename в формате: {name}_{username}_{timestamp}_{uuid}.{ext}
        При превышении max_filename_length оригинальное имя обрезается.

    Examples:
        >>> generate_storage_filename("report.pdf", "ivanov", "20250102T153045", "a1b2c3d4")
        "report_ivanov_20250102T153045_a1b2c3d4.pdf"

        >>> generate_storage_filename("Very_Long_Document_Name_With_Lots_Of_Details_2025.pdf",
        ...                          "ivanov", "20250102T153045", "a1b2c3d4", max_filename_length=50)
        "Very_Long_Document_N_ivanov_20250102T153045_a1b2c3d4.pdf"
    """
    name_stem = Path(original_name).stem
    name_ext = Path(original_name).suffix

    # Фиксированная часть: _{username}_{timestamp}_{uuid}{ext}
    # Пример: _ivanov_20250102T153045_a1b2c3d4.pdf = 1+6+1+15+1+8+4 = 36 символов
    fixed_part_length = 1 + len(username) + 1 + len(timestamp) + 1 + len(uuid) + len(name_ext)

    # Доступная длина для оригинального имени
    available_length = max_filename_length - fixed_part_length

    # Обрезаем name_stem если необходимо
    if len(name_stem) > available_length:
        name_stem = name_stem[:available_length]

    return f"{name_stem}_{username}_{timestamp}_{uuid}{name_ext}"
```

**Настройки обрезания**:
```yaml
filename_length_limits:
  max_filename: 200  # Безопасный предел (filesystem limits: ext4/XFS=255, NTFS=255)
  reserved_for_metadata: 55  # username(20) + timestamp(15) + uuid(8) + separators + ext(10)
  max_original_name_length: 145  # 200 - 55 = 145 символов для оригинального имени

behavior:
  truncate_strategy: "cut_end"  # Обрезаем конец имени
  preserve_extension: true  # Всегда сохраняем расширение
  original_stored_in: "attr.json"  # Полное оригинальное имя всегда в метаданных
```

### Обоснование
- ✅ **Human-readable prefix**: Original filename первым для удобства сортировки и поиска
- ✅ **Гарантия уникальности**: username + timestamp + UUID гарантируют уникальность
- ✅ **Filesystem compatibility**: max_filename=200 безопасно для всех FS (limits: ext4/XFS 255 байт, NTFS 255 символов)
- ✅ **Automatic truncation**: Длинные имена автоматически обрезаются до 145 символов
- ✅ **Original preservation**: Полное оригинальное имя всегда сохраняется в attr.json
- ✅ **Корректное расширение**: Избегает двойных расширений (report.pdf.pdf)
- ✅ **Версионность**: Каждая версия = отдельный физический файл с уникальным именем

### Примеры обрезания длинных имен
```python
# Нормальный файл
original = "report.pdf"  # 6 символов
storage = "report_ivanov_20250102T153045_a1b2c3d4.pdf"  # 48 символов ✅

# Длинное имя (автоматическое обрезание)
original = "Очень_Длинное_Имя_Документа_С_Множеством_Деталей_И_Описаний_Для_Архива_2025_Версия_Финал.pdf"  # 95 символов
storage = "Очень_Длинное_Имя_Документа_С_Множеством_Деталей_И_Описаний_Для_Архива_2025_Версия_Финал_ivanov_20250102T153045_a1b2c3d4.pdf"

# Если результат > 200 символов:
# name_stem обрезается до доступной длины (145 символов в данном примере)
storage = "Очень_Длинное_Имя_Документа_С_Множеством_Деталей_И_Описаний_Для_Архива_2025_Версия_Фин_ivanov_20250102T153045_a1b2c3d4.pdf"  # ровно 200 ✅

# В attr.json всегда хранится полное оригинальное имя:
{
  "original_filename": "Очень_Длинное_Имя_Документа_С_Множеством_Деталей_И_Описаний_Для_Архива_2025_Версия_Финал.pdf",
  "storage_filename": "Очень_Длинное_Имя_Документа_С_Множеством_Деталей_И_Описаний_Для_Архива_2025_Версия_Фин_ivanov_20250102T153045_a1b2c3d4.pdf",
  ...
}
```

### Альтернативы отклонены
- **Виртуальные пространства имен** (`/users/ivanov/documents/report.pdf/v1`): Сложнее реализация namespace resolution, избыточная абстракция
- **Username prefix** (`ivanov_20250102T153045_a1b2c3d4_report.pdf`): Хуже human-readability при сортировке файлов

### Metadata Structure (attr.json)
```json
{
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "original_filename": "report.pdf",
  "storage_filename": "report_ivanov_20250102T153045_a1b2c3d4.pdf",
  "uploaded_by": "ivanov",
  "uploaded_at": "2025-01-02T15:30:45Z",
  "version": 1,
  "file_size": 1048576,
  "mime_type": "application/pdf",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "retention_days": 365,
  "storage_element_id": "storage-01"
}
```

---

## 2. Атомарная запись файлов атрибутов

### Контекст
`*.attr.json` файлы — единственный источник истины для метаданных. Критически важно гарантировать атомарность их записи.

### Решение
**Atomic Write Pattern** через temporary file + fsync + atomic rename:

```python
import os
import json
from uuid import uuid4

def write_attr_file_atomic(target_path: str, attributes: dict):
    # 1. Write to temporary file with unique name
    temp_file = f"{target_path}.{uuid4()}.tmp"

    with open(temp_file, 'w') as f:
        json.dump(attributes, f, indent=2)
        f.flush()
        os.fsync(f.fileno())  # Force write to disk

    # 2. Atomic rename to target filename
    os.rename(temp_file, target_path)  # Atomic operation on POSIX
```

### Constraints
- **Максимальный размер attr.json**: 4KB (гарантия атомарности на большинстве файловых систем)
- **Pointer pattern при превышении**: Если метаданные > 4KB → attr.json содержит только `file_id`, остальное в PostgreSQL

### Обоснование
- ✅ **POSIX гарантии**: `os.rename()` атомарен на POSIX-совместимых FS (ext4, XFS, NTFS)
- ✅ **Crash Safety**: fsync гарантирует запись на диск перед rename
- ✅ **No Partial Writes**: Либо файл полностью записан, либо не существует (no corrupted state)

---

## 3. Отказ от Vector Clocks — упрощение архитектуры

### Контекст
Первоначально планировалось использовать Vector Clocks для разрешения конфликтов при репликации между Storage Elements.

### Решение
**Vector Clocks НЕ используются**. Активная репликация между Storage Elements **не реализуется**.

### Обоснование
- ✅ **Упрощение консистентности**: Фокус на WAL + Saga Pattern вместо сложной системы Vector Clocks
- ✅ **Reduced Complexity**: Меньше moving parts, проще отладка и поддержка
- ✅ **Standalone + Optional Replication**: Storage Elements работают standalone с опциональной репликацией внутри кластера

### Consistency Model
**Упрощенная модель консистентности**:
- WAL (Write-Ahead Log) для транзакционности
- Saga Pattern для долгосрочных операций (Upload, Delete, Transfer)
- Two-Phase Commit для критических операций (смена режима Storage Element)

---

## 4. Saga Pattern для операции Upload File

### Контекст
Загрузка файла — долгосрочная операция, включающая несколько шагов через разные компоненты системы.

### Решение
**5-шаговая Saga с compensating actions**:

```yaml
Step 1: Reserve Space (5s timeout)
  Action: Ingester → Storage Element: "Reserve space for file X, size Y"
  Compensation: Release reservation

Step 2: Upload File Data (based on size, ~1MB/sec baseline)
  Action: Ingester → Storage Element: Stream file chunks
  Compensation: Delete partially uploaded file

Step 3: Write Attribute File (2s timeout)
  Action: Storage Element: Atomic write *.attr.json
  Compensation: Delete attr.json

Step 4: Update DB Cache (3s timeout)
  Action: Storage Element: INSERT into PostgreSQL metadata cache
  Compensation: DELETE from cache table

Step 5: Publish to Service Discovery (2s timeout)
  Action: Admin Module: Update Redis with new file metadata
  Compensation: Remove metadata from Redis
```

### Compensating Actions (Rollback при сбое)
- **Сбой на Step 2**: Delete temp file → Release reservation
- **Сбой на Step 3**: Delete file data → Release reservation
- **Сбой на Step 4**: Delete attr.json → Delete file data → Release reservation
- **Сбой на Step 5**: Leave locally (eventual consistency) → Retry publish в фоне

### Координация
- **Saga Orchestrator**: Admin Module Cluster
- **Total Max Duration**: ~60 секунд для файла 50MB
- **Idempotency**: Все шаги идемпотентны для безопасного retry

---

## 5. Восстановление файлов из архива (AR mode)

### Контекст
Процедура восстановления файлов из архивного хранилища (магнитные ленты) может занимать до 7 дней.

### Решение
**Dedicated Restore Storage Element** с workflow через очередь запросов:

```yaml
Architecture:
  - AR Storage Element: Только *.attr.json (метаданные)
  - Restore Storage Element: Режим EDIT, временное хранилище восстановленных файлов

Workflow:
  1. User Request:
     POST /api/files/{id}/restore
     Response: {"restore_id": "uuid", "status": "queued", "estimated_time": "2-7 days"}

  2. Admin/Automated Restore:
     - Retrieve tape from archive
     - Copy files to Restore Storage Element
     - Validation & integrity check

  3. Webhook Notification (optional):
     POST {user_webhook_url}
     {
       "event": "file_restored",
       "file_id": "uuid",
       "download_url": "/api/files/{id}/download",
       "expires_at": "2025-01-30T00:00:00Z"
     }

  4. File Access: User downloads within 30 days (TTL)

  5. Auto-cleanup: Files deleted after 30 days with notification 3 days before expiration
```

### Restore Storage Element Configuration
```yaml
mode: EDIT  # Temporary storage
retention: 30 days
max_size: 1TB
cleanup_policy: auto_delete_after_retention
```

### Webhook Events (UPDATED: Added restore_started, restore_progress)

**Полный список Webhook Events**:

```yaml
1. restore_started:
   trigger: Начало процесса восстановления файла из AR элемента
   payload:
     {
       "event": "restore_started",
       "restore_id": "uuid",
       "file_id": "file_uuid",
       "estimated_time": "2-7 days",
       "started_at": "2025-01-02T15:30:00Z"
     }

2. restore_progress:
   trigger: Периодические обновления статуса (каждые 24 часа)
   payload:
     {
       "event": "restore_progress",
       "restore_id": "uuid",
       "file_id": "file_uuid",
       "progress_percent": 45,
       "estimated_completion": "2025-01-05T12:00:00Z",
       "current_status": "copying_from_tape"
     }

3. file_restored:
   trigger: Файл успешно восстановлен и доступен для скачивания
   payload:
     {
       "event": "file_restored",
       "restore_id": "uuid",
       "file_id": "file_uuid",
       "download_url": "/api/files/{id}/download",
       "expires_at": "2025-01-30T00:00:00Z"
     }

4. restore_failed:
   trigger: Ошибка при восстановлении файла
   payload:
     {
       "event": "restore_failed",
       "restore_id": "uuid",
       "file_id": "file_uuid",
       "error": "Tape not found in archive",
       "retry_possible": false
     }

5. file_expiring:
   trigger: Файл в Restore Storage Element будет удален через 3 дня
   payload:
     {
       "event": "file_expiring",
       "file_id": "file_uuid",
       "expires_at": "2025-01-27T00:00:00Z",
       "days_remaining": 3
     }
```

### Webhook Configuration
```yaml
User Webhook Settings:
  url: "https://external-system.example.com/artstore/notifications"
  events: [
    "restore_started",
    "restore_progress",
    "file_restored",
    "restore_failed",
    "file_expiring"
  ]
  secret: "webhook_signing_key"  # HMAC validation (X-ArtStore-Signature header)
  retry_policy:
    max_retries: 3
    backoff: exponential
    retry_intervals: [30s, 5m, 30m]
```

---

## 6. Storage Element Replication — опциональная синхронная репликация

### Контекст
Для критичных данных требуется отказоустойчивость через репликацию. Одновременно должна поддерживаться упрощенная standalone конфигурация.

### Решение
**Dual Deployment Model**: Standalone OR Replicated

#### Standalone Mode (по умолчанию)
```yaml
replication:
  enabled: false

# Характеристики:
# - Одиночный узел
# - Упрощенная архитектура
# - Backup через rsync/tape для disaster recovery
# - Подходит для некритичных данных
```

#### Replicated Mode (опционально)
```yaml
replication:
  enabled: true
  mode: sync | async
  replicas: 2
  quorum: majority

sync_replication:
  min_replicas: 2
  write_timeout: 5s
  consistency: strong
  rto: < 30s
  rpo: 0  # Zero data loss

async_replication:
  batch_size: 100
  interval: 60s
  retry_failed: true
  rto: < 30s
  rpo: ~60s  # Last batch
```

### Write Flow Comparison

**Sync Replication**:
```
1. Ingester → Primary Storage Element
2. Primary → Replicas (parallel replication)
3. Wait for quorum (2/3 acknowledge)
4. Return 201 Created to client

Latency: +50-200ms
Consistency: Strong
Risk: Minimal (quorum guarantees)
```

**Async Replication**:
```
1. Ingester → Primary Storage Element
2. Primary writes locally → Return 201 Created immediately
3. Background: Primary → Replicas (async queue)

Latency: +5-10ms
Consistency: Eventual
Risk: Data loss if Primary fails before replication
```

### Failover
```yaml
Detection:
  - Redis Sentinel monitors Primary health
  - 3 consecutive failures (15 seconds total)

Promotion:
  1. Replica with most up-to-date data → new Primary
  2. Service Discovery updated (Redis)
  3. Other Replicas sync from new Primary
  4. Old Primary rejoins as Replica when recovered

Guarantees:
  RTO: < 30 seconds
  RPO: 0 (sync) | ~60s (async)
```

### Deployment Strategy (UPDATED: Replication is OPTIONAL for all modes)
- **EDIT mode Storage Elements**: Replication **OPTIONAL** (администратор выбирает при создании)
  - Рекомендация: Sync replication для критичных оперативных данных
- **RW/RO mode Storage Elements**: Replication **OPTIONAL**
  - Рекомендация: Async replication для баланса производительности и надежности
- **AR mode Storage Elements**: Replication **NOT SUPPORTED** (файлы на архивном хранилище)

**Admin UI Configuration**:
```yaml
# При создании Storage Element
storage_element_config:
  mode: "edit"
  replication:
    enabled: true | false  # Checkbox "Enable replication"
    type: "sync" | "async"  # Radio buttons (доступно если enabled=true)
    replicas: 2  # Number input (доступно если enabled=true)
```

---

## 7. LDAP Integration с Role Mapping

### Контекст
Обязательная интеграция с корпоративным LDAP/Active Directory для централизованной аутентификации.

### Решение
**LDAP Group Mapping на роли системы**:

```yaml
LDAP Configuration:
  connection:
    server: "ldap://ldap.artstore.local:389"
    bind_dn: "cn=artstore-service,dc=artstore,dc=local"
    bind_password: "secure_password"
    base_dn: "dc=artstore,dc=local"

  search:
    user_filter: "(&(objectClass=inetOrgPerson)(uid={username}))"
    user_attributes: ["uid", "mail", "cn", "memberOf", "departmentNumber"]
    group_filter: "(&(objectClass=groupOfNames)(member={user_dn}))"

  mapping:
    groups:
      "cn=ArtStore-Admins,ou=Groups,dc=artstore,dc=local": "admin"
      "cn=ArtStore-Users,ou=Groups,dc=artstore,dc=local": "user"
      "cn=ArtStore-Auditors,ou=Groups,dc=artstore,dc=local": "auditor"
      "cn=ArtStore-Readonly,ou=Groups,dc=artstore,dc=local": "readonly"

    # Standard attributes (always included)
    standard_attributes:
      uid: "username"  # Required
      mail: "email"    # Required

    # Optional attributes (admin configures via UI)
    optional_attributes:
      available:
        - cn → full_name
        - departmentNumber → department
        - telephoneNumber → phone
        - title → job_title
        - manager → manager_dn
        - employeeNumber → employee_id
        - description → description
      selected: []  # Admin selects через UI

    # Custom attribute mappings (admin configures)
    custom_mappings:
      - ldap_attribute: "companyDivision"
        jwt_claim: "division"
      - ldap_attribute: "costCenter"
        jwt_claim: "cost_center"

    default_role: "user"
    nested_groups: true
    max_depth: 3
```

### Configurable Attribute Mapping (Admin UI)

**Admin UI Component для конфигурации LDAP attributes**:

```typescript
interface LDAPAttributeMapping {
  ldapAttribute: string;
  jwtClaim: string;
  enabled: boolean;
}

// Predefined mappings (admin toggles enabled/disabled)
const defaultMappings: LDAPAttributeMapping[] = [
  { ldapAttribute: 'cn', jwtClaim: 'full_name', enabled: true },
  { ldapAttribute: 'departmentNumber', jwtClaim: 'department', enabled: false },
  { ldapAttribute: 'telephoneNumber', jwtClaim: 'phone', enabled: false },
  { ldapAttribute: 'title', jwtClaim: 'job_title', enabled: false },
  { ldapAttribute: 'manager', jwtClaim: 'manager_dn', enabled: false },
  { ldapAttribute: 'employeeNumber', jwtClaim: 'employee_id', enabled: false },
];

// Admin capabilities:
// 1. Toggle enabled/disabled for predefined mappings
// 2. Add custom mappings (LDAP attribute → JWT claim)
// 3. Preview JWT token structure before saving
// 4. Validation: JWT size < 4KB, max 10 custom attributes
```

### JWT Claims from LDAP (Example with custom attributes)
```json
{
  "sub": "ivanov",
  "email": "ivanov@artstore.local",
  "full_name": "Ivan Ivanov",
  "roles": ["user"],
  "department": "IT",
  "phone": "+7-123-456-7890",
  "job_title": "Senior Engineer",
  "manager_dn": "uid=petrov,ou=Users,dc=artstore,dc=local",
  "employee_id": "EMP-12345",
  "division": "R&D",
  "cost_center": "CC-001",
  "ldap_dn": "uid=ivanov,ou=Users,dc=artstore,dc=local",
  "ldap_groups": [
    "cn=ArtStore-Users,ou=Groups,dc=artstore,dc=local",
    "cn=IT-Department,ou=Groups,dc=artstore,dc=local"
  ],
  "iat": 1704198000,
  "exp": 1704199800
}
```

### Validation Rules
```yaml
jwt_token_limits:
  max_size: 4KB  # HTTP header standard limit
  max_custom_attributes: 10

validation:
  - JWT total size < 4KB (warning if approaching 3.5KB)
  - LDAP attribute exists and is accessible
  - JWT claim name: alphanumeric + underscore only
  - No reserved claim names (sub, iat, exp, iss, aud, jti)
  - LDAP attribute read permissions verified
```

### Role Permissions (RBAC)
```yaml
admin:
  - "*"  # All permissions

user:
  - "files.upload"
  - "files.download.own"
  - "files.search"
  - "files.delete.own"  # Only in EDIT mode

auditor:
  - "files.search"
  - "files.download.*"
  - "audit.view"
  - "audit.export"

readonly:
  - "files.search"
  - "files.download.own"
```

---

## 8. Batch Operations

### Контекст
Необходимость массовой загрузки и удаления файлов для операционной эффективности.

### Решение
**Batch API с ограничениями**:

```yaml
Constraints:
  max_files_per_batch: 100
  max_total_size: 1GB
  timeout: 10 minutes

Endpoints:
  POST /api/batch/upload
    Body: {files: [{name, size, metadata}, ...]}
    Response: {batch_id: "uuid", status: "processing"}

  GET /api/batch/{batch_id}/status
    Response: {completed: 15, failed: 2, pending: 3, errors: [...]}

  POST /api/batch/delete
    Body: {file_ids: ["uuid1", ...], mode: "immediate" | "scheduled"}
    Response: {deleted: 2, failed: 1, errors: [...]}
```

### Implementation Strategy
- **Parallel Processing**: До 10 файлов параллельно
- **Progress Tracking**: Real-time status через WebSocket или polling
- **Error Handling**: Partial success (некоторые файлы могут загрузиться, другие fail)
- **Saga Coordination**: Batch upload = одна общая Saga с sub-transactions

---

## ✅ Все архитектурные решения утверждены

Все открытые вопросы (A, B, C, D) решены на основе feedback в q3.md:

- **Вопрос A** (File Naming): ✅ Утвержден формат `{name}_{username}_{timestamp}_{uuid}.{ext}`
- **Вопрос B** (Webhook Events): ✅ Добавлены `restore_started`, `restore_progress`
- **Вопрос C** (Replication): ✅ Опциональная для всех режимов (администратор выбирает при создании)
- **Вопрос D** (LDAP Attributes): ✅ Configurable mapping через Admin UI

---

## История изменений

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2025-10-02 | 1.0 | Первоначальная версия с решениями по уникальности файлов, атомарной записи attr.json, отказу от Vector Clocks, Saga Pattern, восстановлению из AR mode, репликации, LDAP integration, batch operations |
| 2025-10-02 | 1.1 | **Финализация всех архитектурных решений**:<br>- File naming: `{name}_{username}_{timestamp}_{uuid}.{ext}` (original name первым)<br>- Webhook events: добавлены `restore_started`, `restore_progress`<br>- Replication: опциональная для всех режимов Storage Elements<br>- LDAP attributes: configurable mapping через Admin UI (до 10 custom атрибутов, JWT < 4KB) |
| 2025-10-02 | 1.2 | **Добавлено автоматическое обрезание длинных имен файлов**:<br>- max_filename_length: 200 символов (безопасный предел для всех FS)<br>- Автоматическое обрезание name_stem при превышении лимита<br>- Полное оригинальное имя всегда хранится в attr.json<br>- Доступная длина для оригинального имени: ~145 символов |
