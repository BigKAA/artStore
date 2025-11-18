# ArtStore Admin UI - Техническая спецификация

**Версия**: 1.0
**Дата**: 2025-11-17
**Статус**: Draft - Требует утверждения

---

## 1. Обзор системы

### 1.1 Назначение

Веб-интерфейс администратора для управления распределенной системой файлового хранилища ArtStore. Предоставляет централизованный доступ к управлению:
- Учетными записями администраторов
- Service accounts (клиентами API)
- Элементами хранения (Storage Elements)
- Файлами в системе
- Мониторингом и метриками

### 1.2 Целевая аудитория

Системные администраторы, управляющие инфраструктурой ArtStore. Интерфейс не оптимизируется для мобильных устройств - только desktop браузеры.

### 1.3 Технологический стек

- **Frontend Framework**: Angular v20
- **UI Framework**: Bootstrap 5 (стандартные компоненты)
- **State Management**: NgRx (Redux pattern)
- **HTTP Client**: Angular HttpClient с JWT interceptors
- **Build Tool**: Angular CLI
- **Browser Support**: Только современные браузеры (Chrome, Firefox, Edge - последние версии)
- **Network Mode**: Online only (offline support не требуется)

---

## 2. Аутентификация и авторизация

### 2.1 Механизм аутентификации

**Тип**: Локальные учетные записи администраторов (отдельно от OAuth 2.0 service accounts)

**Функционал**:
- Login/Password форма аутентификации
- JWT токены для поддержания сессии
- Автоматический refresh токенов
- Logout с инвалидацией токенов

**Backend API** (требуется реализация в admin-module):
```http
POST /api/admin-auth/login
Request: { "username": "string", "password": "string" }
Response: { "access_token": "jwt", "refresh_token": "jwt", "expires_in": 1800 }

POST /api/admin-auth/refresh
Request: { "refresh_token": "jwt" }
Response: { "access_token": "jwt", "expires_in": 1800 }

POST /api/admin-auth/logout
Authorization: Bearer <token>
Response: { "success": true }
```

### 2.2 Роли администраторов (начальный этап)

На первой итерации:
- **admin** - полный доступ ко всем функциям

Будущие роли (для дальнейшего развития):
- **super-admin** - управление другими админами
- **read-only-admin** - только просмотр
- **storage-admin** - управление только storage elements

### 2.3 Управление учетными записями администраторов

**Функционал** (для super-admin роли в будущем):
- Создание новых admin аккаунтов
- Изменение паролей
- Деактивация аккаунтов
- Назначение ролей

**Начальный этап**: Создание admin аккаунтов через CLI или прямую вставку в БД.

---

## 3. Структура интерфейса

### 3.1 Layout компоненты

#### 3.1.1 Top Navigation Bar

**Элементы**:
- **Логотип**: "ArtStore Admin" (слева)
- **Навигационное меню**:
  - Dashboard (🏠)
  - Service Accounts (👥)
  - Storage Elements (💾)
  - File Manager (📁)
  - Metrics (📊)
- **Справа**:
  - Theme toggle (☀️/🌙 Light/Dark mode)
  - User dropdown:
    - Username display
    - Settings (будущее)
    - Logout

**Технологии**: Bootstrap 5 Navbar component

#### 3.1.2 Main Content Area

- Responsive container для основного контента
- Breadcrumbs навигация
- Page header с заголовком и action buttons

#### 3.1.3 Toast Notifications

**Позиция**: Top-right corner
**Типы**: Success, Error, Warning, Info
**Поведение**:
- Автоматическое скрытие через 5 секунд
- Кнопка закрытия (×)
- Настройка: возможность глобально отключить success notifications

**Технология**: Bootstrap Toast или ngx-toastr

---

## 4. Экраны и функционал

### 4.1 Dashboard (Общая консоль)

**URL**: `/dashboard`

#### 4.1.1 Текущее состояние модулей

**Компонент**: Service Status Grid

**Отображаемые модули**:
- Admin Module Cluster (порты 8000-8009)
- Storage Elements (8010-8019)
- Ingester Cluster (8020-8029)
- Query Cluster (8030-8039)

**Информация по каждому модулю**:
- **Health Status**:
  - 🟢 Healthy (все /health/ready checks passed)
  - 🟡 Degraded (частичная недоступность)
  - 🔴 Down (недоступен)
- **Метрики производительности**:
  - CPU Usage (%)
  - Memory Usage (MB / GB)
  - Disk Space (available / total)
- **Network Metrics**:
  - Active Connections
  - Requests per Second (RPS)
  - Average Response Time (ms)
- **Alerts & Warnings**:
  - Критические ошибки (красный badge)
  - Предупреждения (желтый badge)

**Real-time обновление**: WebSocket или polling каждые 5 секунд

**API Endpoint**:
```http
GET /api/admin/system/status
Response: {
  "modules": [
    {
      "name": "Admin Module",
      "type": "admin-module",
      "instances": [
        {
          "id": "admin-1",
          "url": "http://localhost:8000",
          "status": "healthy",
          "cpu_percent": 15.5,
          "memory_mb": 512,
          "disk_available_gb": 45.2,
          "disk_total_gb": 100,
          "active_connections": 12,
          "rps": 150,
          "avg_response_time_ms": 25,
          "alerts": []
        }
      ]
    }
  ],
  "timestamp": "2025-11-17T10:30:00Z"
}
```

#### 4.1.2 Быстрые ссылки

**Компонент**: Quick Actions Cards

- **Service Accounts**: "Создать новый service account" → navigate to create form
- **Storage Elements**: "Добавить storage element" → navigate to create form
- **File Manager**: "Найти файл" → navigate to file search

#### 4.1.3 Статистика системы

**Компонент**: Statistics Overview

**Метрики**:
- Total Service Accounts: XXX
- Active Storage Elements: XX (edit: X, rw: X, ro: X, ar: X)
- Total Files Stored: XXX,XXX
- Total Storage Used: XX.X TB / YY.Y TB
- Files Uploaded Today: XXX
- Files Downloaded Today: XXX

**Графики** (простые, без Grafana):
- Storage Usage Trend (last 7 days) - line chart
- Upload/Download Activity (last 24 hours) - bar chart

**Технология**: Chart.js или ng2-charts

---

### 4.2 Service Accounts Management

**URL**: `/service-accounts`

#### 4.2.1 Service Accounts List

**Компонент**: Service Accounts Table

**Columns**:
- **Select** (checkbox для bulk operations)
- **Name** (sortable)
- **Client ID** (copyable, показывать первые 8 символов + "...")
- **Role** (badge: ADMIN/USER/READONLY)
- **Status** (badge: Active/Disabled)
- **Created At** (sortable, format: "YYYY-MM-DD HH:mm")
- **Last Used** (sortable, format: "X days ago")
- **Actions** (dropdown):
  - 👁️ View Details
  - ✏️ Edit
  - 🔄 Rotate Secret
  - 🔗 Manage Webhooks
  - 🗑️ Delete

**Pagination**:
- Items per page: 10, 25, 50, 100 (dropdown selector)
- Page navigation: « Previous | 1 2 3 ... 10 | Next »
- Total count: "Showing 1-25 of 243 service accounts"

**Filters** (Accordion collapse panel):
- **Role**: Dropdown (All, ADMIN, USER, READONLY)
- **Status**: Dropdown (All, Active, Disabled)
- **Search**: Text input (search by name or client_id)
- **Date Range**: From/To date picker (filter by created_at)

**Bulk Operations** (toolbar над таблицей):
- **Bulk Delete**: With confirmation modal
- **Bulk Role Change**: Modal с выбором новой роли
- **Bulk Enable/Disable**: Toggle status

**API Endpoints**:
```http
GET /api/service-accounts?page=1&limit=25&role=ADMIN&status=active&search=test&from=2025-01-01&to=2025-12-31
Response: {
  "items": [ /* service account objects */ ],
  "total": 243,
  "page": 1,
  "limit": 25,
  "pages": 10
}

DELETE /api/service-accounts/bulk
Request: { "ids": ["uuid1", "uuid2"] }
Response: { "deleted": 2, "failed": [] }

PATCH /api/service-accounts/bulk/role
Request: { "ids": ["uuid1"], "role": "ADMIN" }
Response: { "updated": 1, "failed": [] }

PATCH /api/service-accounts/bulk/status
Request: { "ids": ["uuid1"], "enabled": false }
Response: { "updated": 1, "failed": [] }
```

#### 4.2.2 Create Service Account

**URL**: `/service-accounts/create`

**Компонент**: Create Service Account Form (Modal или отдельная страница)

**Поля формы**:
- **Name*** (required, text input, max 100 chars)
- **Description** (textarea, max 500 chars)
- **Client ID*** (required, text input, ручной ввод)
  - Validation: уникальность, формат UUID или custom format
- **Client Secret*** (required, password input, ручной ввод)
  - Validation: минимум 32 символа
  - Toggle visibility button (👁️)
  - Generate Random button (генерация secure random string)
- **Role*** (required, dropdown: ADMIN/USER/READONLY)
- **Enabled** (toggle switch, default: true)

**Validation**:
- Client ID уникальность проверяется через API
- Client Secret strength indicator (weak/medium/strong)

**Actions**:
- **Create** button (primary)
- **Cancel** button (secondary)

**API Endpoint**:
```http
POST /api/service-accounts
Request: {
  "name": "string",
  "description": "string",
  "client_id": "string",
  "client_secret": "string",
  "role": "ADMIN",
  "enabled": true
}
Response: {
  "id": "uuid",
  "name": "string",
  "client_id": "string",
  "role": "ADMIN",
  "created_at": "2025-11-17T10:30:00Z"
}
```

#### 4.2.3 View Service Account Details

**URL**: `/service-accounts/:id`

**Компонент**: Service Account Details (Modal)

**Разделы**:

**1. General Information**:
- Name
- Description
- Client ID (copyable)
- Client Secret (hidden по умолчанию, кнопка "Show Secret" → показывает на 10 секунд)
- Role (badge)
- Status (badge)
- Created At
- Updated At
- Last Used At

**2. Activity Log** (будущее):
- Recent API calls (last 10)
- Authentication attempts

**3. Webhooks** (будущее):
- List of configured webhooks
- Add/Edit/Delete webhook endpoints

**Actions**:
- **Edit** button
- **Rotate Secret** button
- **Delete** button
- **Close** button

#### 4.2.4 Edit Service Account

**URL**: `/service-accounts/:id/edit`

**Компонент**: Edit Service Account Form (Modal)

**Editable fields**:
- Name
- Description
- Role
- Enabled status

**Non-editable fields** (displayed as read-only):
- UUID (ID)
- Client ID
- Client Secret (separate action for rotation)
- Created At

**API Endpoint**:
```http
PATCH /api/service-accounts/:id
Request: {
  "name": "string",
  "description": "string",
  "role": "ADMIN",
  "enabled": true
}
Response: { /* updated service account */ }
```

#### 4.2.5 Rotate Secret

**Trigger**: Button "Rotate Secret" в деталях или в edit форме

**Компонент**: Rotate Secret Modal

**Workflow**:
1. Показать предупреждение: "This will invalidate the current secret. Continue?"
2. После подтверждения - generate new secret
3. Показать новый secret в copyable поле с предупреждением: "Save this secret now. It will not be shown again."
4. Client должен скопировать новый secret перед закрытием modal

**API Endpoint**:
```http
POST /api/service-accounts/:id/rotate-secret
Response: {
  "client_secret": "new-generated-secret"
}
```

**Вопрос для уточнения**: Автоматическая генерация секрета или возможность ручного ввода?

#### 4.2.6 Webhooks Management (будущее)

**URL**: `/service-accounts/:id/webhooks`

**Компонент**: Webhooks Management (Modal или отдельная страница)

**Функционал**:
- List of webhook endpoints
- Add new webhook (URL, events to subscribe)
- Edit webhook
- Delete webhook
- Test webhook (send test event)

**События для подписки**:
- file_restored
- restore_failed
- file_expiring

**Вопрос для уточнения**: Какие именно события webhook должны поддерживаться?

---

### 4.3 Storage Elements Management

**URL**: `/storage-elements`

#### 4.3.1 Storage Elements List

**Компонент**: Storage Elements Table

**Columns**:
- **Name** (sortable)
- **Mode** (badge: edit 🟢 / rw 🟡 / ro 🔵 / ar ⚪)
- **Storage Type** (icon + text: Local FS 📁 / S3 ☁️)
- **Retention Period** (sortable, format: "X years" или "X days")
- **Time Until Expiration** (sortable, color-coded):
  - Green: > 1 year → "X years"
  - Yellow: 30 days - 1 year → "X days"
  - Red: < 30 days → "⚠️ X days"
- **Capacity** (progress bar: used / total)
- **File Count** (number)
- **Actions** (dropdown):
  - 👁️ View Details
  - ✏️ Edit
  - 🔄 Change Mode
  - 📊 View Metrics
  - 📁 Browse Files
  - 🗑️ Delete

**Pagination**: Same as Service Accounts (10/25/50/100 items per page)

**Filters** (Accordion collapse panel):
- **Mode**: Multi-select (edit, rw, ro, ar)
- **Storage Type**: Multi-select (Local FS, S3)
- **Retention Period**: Range slider (0-10 years)
- **Search**: Text input (search by name)

**Sorting**:
- By Storage Type (Local FS first / S3 first)
- By Retention Period (ascending / descending)
- By Time Until Expiration (urgent first)
- By Capacity Usage (% used)

**API Endpoint**:
```http
GET /api/storage-elements?page=1&limit=25&mode=edit,rw&type=local&search=storage1
Response: {
  "items": [
    {
      "id": "uuid",
      "name": "Storage Element 01",
      "mode": "edit",
      "storage_type": "local",
      "retention_years": 5,
      "expiration_date": "2030-11-17",
      "days_until_expiration": 1826,
      "capacity_total_gb": 1000,
      "capacity_used_gb": 450,
      "file_count": 15234,
      "url": "http://localhost:8010"
    }
  ],
  "total": 15,
  "page": 1,
  "limit": 25
}
```

#### 4.3.2 Add Storage Element

**URL**: `/storage-elements/create`

**Компонент**: Create Storage Element Form (Modal или отдельная страница)

**Поля формы**:

**1. Basic Information**:
- **Name*** (required, text input, max 100 chars)
- **Description** (textarea, max 500 chars)
- **URL*** (required, text input, format validation: http(s)://...)
  - Example: "http://localhost:8010"

**2. Storage Configuration**:
- **Storage Type*** (required, radio buttons):
  - 📁 Local Filesystem
  - ☁️ S3 Compatible (MinIO, AWS S3)
- **Capacity (GB)*** (required, number input)
- **Retention Period (Years)*** (required, number input, 1-50)

**3. Local Filesystem Settings** (показывается если type=local):
- **Base Path*** (required, text input)
  - Example: "/data/storage"

**4. S3 Settings** (показывается если type=s3):
- **Endpoint URL*** (required, text input)
  - Example: "http://localhost:9000"
- **Bucket Name*** (required, text input)
- **Access Key*** (required, text input)
- **Secret Key*** (required, password input)
- **Region** (optional, text input, default: "us-east-1")

**5. Initial Mode**:
- **Mode*** (required, radio buttons):
  - 🟢 edit (Read-Write-Delete, default)
  - 🟡 rw (Read-Write only)
  - 🔵 ro (Read-only)
  - ⚪ ar (Archive mode)

**Validation**:
- URL reachability test (optional button "Test Connection")
- S3 credentials verification

**Actions**:
- **Create** button
- **Test Connection** button (validate settings before creation)
- **Cancel** button

**API Endpoint**:
```http
POST /api/storage-elements
Request: {
  "name": "string",
  "description": "string",
  "url": "http://localhost:8010",
  "storage_type": "local",
  "capacity_gb": 1000,
  "retention_years": 5,
  "local": {
    "base_path": "/data/storage"
  },
  "s3": {
    "endpoint_url": "http://localhost:9000",
    "bucket_name": "artstore-files",
    "access_key": "minioadmin",
    "secret_key": "minioadmin",
    "region": "us-east-1"
  },
  "mode": "edit"
}
Response: { /* created storage element */ }
```

#### 4.3.3 View Storage Element Details

**URL**: `/storage-elements/:id`

**Компонент**: Storage Element Details (Modal)

**Разделы**:

**1. General Information**:
- Name
- Description
- URL (link)
- Storage Type
- Mode (badge с цветом)
- Created At
- Updated At

**2. Capacity & Retention**:
- Total Capacity (GB)
- Used Capacity (GB) + progress bar
- Available Capacity (GB)
- Usage Percentage (%)
- Retention Period (years)
- Expiration Date
- Days Until Expiration (color-coded)

**3. Storage Configuration**:
- Local FS Base Path (if type=local)
- S3 Endpoint, Bucket, Region (if type=s3)

**4. Statistics**:
- Total Files Stored
- Files Added Today / This Week
- Average File Size
- Growth Rate (GB per day)

**5. Current Alerts**:
- ⚠️ Retention period expiring soon (< 30 days)
- ⚠️ Capacity above 80%
- ⚠️ Capacity above 90%
- 🔴 Capacity above 95%

**Actions**:
- **Edit** button
- **Change Mode** button
- **Delete** button
- **Browse Files** button → navigate to File Manager filtered by this storage
- **Close** button

#### 4.3.4 Edit Storage Element

**URL**: `/storage-elements/:id/edit`

**Компонент**: Edit Storage Element Form (Modal)

**Editable fields**:
- Name
- Description
- Capacity (GB)
- Retention Period (Years)
- Storage configuration (Local path or S3 credentials)

**Non-editable fields** (read-only):
- UUID (ID)
- URL
- Storage Type (cannot change local ↔ s3)
- Mode (separate action)

**API Endpoint**:
```http
PATCH /api/storage-elements/:id
Request: { /* editable fields */ }
Response: { /* updated storage element */ }
```

#### 4.3.5 Change Mode

**Trigger**: Button "Change Mode" в деталях или таблице

**Компонент**: Change Mode Modal

**Workflow**:
1. **Показать текущий режим**: "Current mode: edit 🟢"
2. **Выбрать новый режим** (dropdown):
   - edit → rw (allowed)
   - rw → ro (allowed)
   - ro → ar (allowed)
   - ar → other (not allowed via UI, только через конфигурацию)
3. **Предупреждение**:
   ```
   ⚠️ WARNING: After changing the mode to [new_mode], you MUST:

   1. Update the storage-element configuration file
   2. Restart the storage-element service

   Mode transition rules:
   - edit → rw: Files can no longer be deleted
   - rw → ro: Files can no longer be added or modified
   - ro → ar: Files metadata only, physical files moved to cold storage

   This operation cannot be reversed via UI.
   ```
4. **Confirmation checkbox**: "I understand that I need to update configuration file and restart the service"
5. **Actions**:
   - **Change Mode** button (disabled until checkbox checked)
   - **Cancel** button

**API Endpoint**:
```http
POST /api/storage-elements/:id/change-mode
Request: { "new_mode": "rw" }
Response: {
  "id": "uuid",
  "mode": "rw",
  "previous_mode": "edit",
  "changed_at": "2025-11-17T10:30:00Z"
}
```

#### 4.3.6 Storage Element Monitoring

**Компонент**: Real-time Metrics Chart (embedded in details page)

**Метрики**:
- **Storage Usage Over Time** (line chart, last 7/30 days)
- **File Upload/Download Activity** (bar chart, last 24 hours)
- **Growth Rate** (GB per day, trend line)

**Alert Indicators**:
- 🟢 Healthy: capacity < 80%, retention > 90 days
- 🟡 Warning: capacity 80-90%, retention 30-90 days
- 🔴 Critical: capacity > 90%, retention < 30 days

---

### 4.4 File Manager

**URL**: `/files`

**Приоритет**: Низкий (реализация в Phase 3)

#### 4.4.1 File Search

**Компонент**: File Search Form + Results Table

**Поля поиска** (search by attributes):
- **Filename** (text input, partial match)
- **Username** (who uploaded, text input)
- **Upload Date Range** (from/to date picker)
- **Storage Element** (multi-select dropdown)
- **File Extension** (dropdown: .pdf, .docx, .xlsx, .jpg, etc.)
- **File Size Range** (min/max in MB)
- **Custom Attributes** (key-value pairs, advanced search)

**Search Results Table**:

**Columns**:
- **Filename** (original name, sortable)
- **Storage Filename** (actual stored name with UUID)
- **Username** (uploaded by)
- **Upload Date** (sortable)
- **File Size** (sortable, human-readable: KB/MB/GB)
- **Storage Element** (name)
- **Storage Mode** (badge: edit/rw/ro/ar)
- **Actions** (dropdown):
  - 👁️ View Metadata
  - ⬇️ Download
  - 🔄 Transfer (only from ro to edit)
  - 🗑️ Delete (only if storage mode = edit)

**Pagination**: Настраиваемая (10/25/50/100/500 items per page)

**API Endpoint**:
```http
GET /api/files/search?filename=report&username=ivanov&from=2025-01-01&to=2025-12-31&storage_element_id=uuid&ext=pdf&size_min=1&size_max=100&page=1&limit=50
Response: {
  "items": [
    {
      "id": "uuid",
      "original_filename": "report.pdf",
      "storage_filename": "report_ivanov_20250109T120530_a1b2c3d4.pdf",
      "username": "ivanov",
      "upload_date": "2025-01-09T12:05:30Z",
      "file_size_bytes": 1048576,
      "file_size_human": "1.0 MB",
      "storage_element_id": "uuid",
      "storage_element_name": "Storage 01",
      "storage_mode": "edit",
      "attributes": { /* attr.json content */ }
    }
  ],
  "total": 1523,
  "page": 1,
  "limit": 50
}
```

#### 4.4.2 View File Metadata

**Компонент**: File Metadata Modal

**Отображение**:
- **Original Filename**
- **Storage Filename** (copyable)
- **Username** (uploaded by)
- **Upload Date & Time**
- **File Size**
- **Storage Element** (name + mode)
- **File Path** (on storage)
- **MIME Type**
- **Custom Attributes** (JSON tree view с подсветкой синтаксиса)
  - Full content of `*.attr.json`

**Actions**:
- **Download** button
- **Copy JSON** button (copy full attr.json to clipboard)
- **Close** button

#### 4.4.3 Download File

**Trigger**: Button "Download" в таблице или в metadata modal

**Workflow**:
1. Отправить запрос к API
2. Получить signed URL или stream файла
3. Trigger browser download

**API Endpoint**:
```http
GET /api/files/:id/download
Response:
- Option 1: Redirect to signed URL
- Option 2: Stream file content with Content-Disposition header
```

#### 4.4.4 Delete File

**Trigger**: Button "Delete" (только для edit mode storage)

**Компонент**: Delete Confirmation Modal

**Workflow**:
1. Проверить что storage mode = edit
2. Показать предупреждение:
   ```
   ⚠️ WARNING: This action cannot be undone.

   File: report.pdf
   Uploaded by: ivanov
   Upload date: 2025-01-09

   This will permanently delete:
   - Physical file from storage
   - Attribute file (*.attr.json)
   - Database cache entry
   ```
3. Confirmation input: "Type DELETE to confirm"
4. **Actions**:
   - **Delete** button (enabled after typing DELETE)
   - **Cancel** button

**API Endpoint**:
```http
DELETE /api/files/:id
Response: { "success": true, "deleted_at": "2025-11-17T10:30:00Z" }
```

#### 4.4.5 Transfer File

**Trigger**: Button "Transfer" (только из ro → edit storage)

**Компонент**: Transfer File Modal

**Workflow**:
1. Проверить что source storage mode = ro
2. **Select Target Storage**:
   - Dropdown со списком storage elements в режиме edit
   - Показать доступное место на каждом storage
3. **Confirmation**:
   ```
   Transfer file from:
   - Source: Storage 02 (ro mode)

   To:
   - Target: Storage 01 (edit mode)

   File will be:
   - Copied to target storage
   - Removed from source storage (if option checked)

   ☑️ Delete from source after successful transfer
   ```
4. **Actions**:
   - **Transfer** button
   - **Cancel** button

**API Endpoint**:
```http
POST /api/files/:id/transfer
Request: {
  "target_storage_id": "uuid",
  "delete_from_source": true
}
Response: {
  "success": true,
  "new_file_id": "uuid",
  "transferred_at": "2025-11-17T10:30:00Z"
}
```

---

### 4.5 Metrics & Monitoring

**URL**: `/metrics`

**Приоритет**: Phase 2

#### 4.5.1 Grafana Embed

**Компонент**: Grafana Dashboard Iframe

**Функционал**:
- **Embedded Grafana**: Full-screen iframe с Grafana dashboards
- **Multiple Dashboards** (tabs или dropdown selector):
  - System Overview (CPU, Memory, Disk)
  - Storage Elements Performance
  - File Operations (Uploads, Downloads, Deletes)
  - Authentication & Authorization (JWT tokens, login attempts)

**Configuration**:
- Grafana URL (configurable via environment variable)
- Dashboard IDs (configurable)
- Auto-refresh interval (default: 30 seconds)

**Пример**:
```html
<iframe
  src="http://localhost:3000/d/dashboard-id?orgId=1&theme=light&kiosk=tv"
  width="100%"
  height="800px"
  frameborder="0">
</iframe>
```

**Theme Integration**:
- Light mode → Grafana light theme
- Dark mode → Grafana dark theme

---

## 5. Design System

### 5.1 Цветовая палитра

**Primary Color**: Салатовый (Lime Green)
- Primary: `#A3D977` (салатовый)
- Primary Dark: `#8BC34A` (более насыщенный салатовый)
- Primary Light: `#C5E1A5` (светло-салатовый)

**Secondary Colors** (светлые тона):
- Secondary: `#81C784` (мятный зеленый)
- Info: `#64B5F6` (светло-голубой)
- Warning: `#FFD54F` (светло-желтый)
- Danger: `#E57373` (светло-красный)
- Success: `#81C784` (светло-зеленый)

**Neutral Colors**:
- Light Background: `#FAFAFA`
- Dark Background: `#263238`
- Text Primary: `#212121`
- Text Secondary: `#757575`
- Border: `#E0E0E0`

### 5.2 Typography

**Шрифты**: Bootstrap 5 default fonts (system fonts)
```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
```

**Размеры**:
- H1: 2.5rem (40px)
- H2: 2rem (32px)
- H3: 1.75rem (28px)
- H4: 1.5rem (24px)
- Body: 1rem (16px)
- Small: 0.875rem (14px)

### 5.3 Spacing

Bootstrap 5 spacing scale (rem based):
- `0`: 0
- `1`: 0.25rem (4px)
- `2`: 0.5rem (8px)
- `3`: 1rem (16px)
- `4`: 1.5rem (24px)
- `5`: 3rem (48px)

### 5.4 Bootstrap Components Customization

**Используем стандартные Bootstrap 5 компоненты**:
- Buttons
- Forms (inputs, selects, textareas)
- Tables
- Modals
- Toasts
- Navbar
- Cards
- Badges
- Progress bars
- Dropdowns
- Pagination

**Customization через SCSS variables**:
```scss
$primary: #A3D977;
$secondary: #81C784;
$success: #81C784;
$info: #64B5F6;
$warning: #FFD54F;
$danger: #E57373;

$body-bg: #FAFAFA;
$body-color: #212121;

$border-radius: 0.375rem;
$font-size-base: 1rem;
```

### 5.5 Theme Toggle (Light/Dark Mode)

**Implementation**:
- Toggle switch в navbar (справа)
- State management: NgRx store
- Persistence: localStorage (`theme: 'light' | 'dark'`)
- CSS variables для динамического переключения цветов

**CSS Variables**:
```css
:root {
  --bg-primary: #FAFAFA;
  --bg-secondary: #FFFFFF;
  --text-primary: #212121;
  --text-secondary: #757575;
}

[data-theme="dark"] {
  --bg-primary: #263238;
  --bg-secondary: #37474F;
  --text-primary: #FFFFFF;
  --text-secondary: #B0BEC5;
}
```

---

## 6. Angular Project Structure

### 6.1 Module Organization

```
src/app/
├── core/                          # Singleton services, guards, interceptors
│   ├── auth/
│   │   ├── auth.service.ts        # Authentication logic
│   │   ├── auth.guard.ts          # Route guard
│   │   ├── auth.interceptor.ts    # JWT token interceptor
│   │   └── auth.models.ts         # Auth interfaces
│   ├── api/
│   │   ├── api.service.ts         # Base HTTP service
│   │   ├── api.config.ts          # API configuration
│   │   └── api.models.ts          # Common API interfaces
│   ├── theme/
│   │   ├── theme.service.ts       # Theme management
│   │   └── theme.models.ts
│   └── core.module.ts
│
├── shared/                        # Reusable components, directives, pipes
│   ├── components/
│   │   ├── toast/                 # Toast notifications
│   │   ├── confirmation-modal/    # Reusable confirmation dialog
│   │   ├── table-pagination/      # Pagination component
│   │   └── loading-spinner/       # Loading indicator
│   ├── directives/
│   │   ├── copyable.directive.ts  # Copy to clipboard
│   │   └── tooltip.directive.ts
│   ├── pipes/
│   │   ├── file-size.pipe.ts      # Bytes to human-readable
│   │   ├── time-ago.pipe.ts       # Relative time
│   │   └── highlight.pipe.ts      # Text highlighting
│   └── shared.module.ts
│
├── features/                      # Feature modules
│   ├── auth/
│   │   ├── login/
│   │   │   ├── login.component.ts
│   │   │   ├── login.component.html
│   │   │   └── login.component.scss
│   │   └── auth-routing.module.ts
│   │
│   ├── dashboard/
│   │   ├── components/
│   │   │   ├── service-status-grid/
│   │   │   ├── quick-actions/
│   │   │   └── statistics-overview/
│   │   ├── dashboard.component.ts
│   │   └── dashboard-routing.module.ts
│   │
│   ├── service-accounts/
│   │   ├── components/
│   │   │   ├── service-accounts-list/
│   │   │   ├── service-account-details/
│   │   │   ├── service-account-form/
│   │   │   └── rotate-secret-modal/
│   │   ├── services/
│   │   │   └── service-accounts.service.ts
│   │   ├── store/                 # NgRx state
│   │   │   ├── service-accounts.actions.ts
│   │   │   ├── service-accounts.reducer.ts
│   │   │   ├── service-accounts.effects.ts
│   │   │   └── service-accounts.selectors.ts
│   │   └── service-accounts-routing.module.ts
│   │
│   ├── storage-elements/
│   │   ├── components/
│   │   │   ├── storage-elements-list/
│   │   │   ├── storage-element-details/
│   │   │   ├── storage-element-form/
│   │   │   └── change-mode-modal/
│   │   ├── services/
│   │   │   └── storage-elements.service.ts
│   │   ├── store/
│   │   │   ├── storage-elements.actions.ts
│   │   │   ├── storage-elements.reducer.ts
│   │   │   ├── storage-elements.effects.ts
│   │   │   └── storage-elements.selectors.ts
│   │   └── storage-elements-routing.module.ts
│   │
│   ├── files/
│   │   ├── components/
│   │   │   ├── file-search/
│   │   │   ├── file-list/
│   │   │   ├── file-metadata-modal/
│   │   │   └── transfer-file-modal/
│   │   ├── services/
│   │   │   └── files.service.ts
│   │   ├── store/
│   │   │   ├── files.actions.ts
│   │   │   ├── files.reducer.ts
│   │   │   ├── files.effects.ts
│   │   │   └── files.selectors.ts
│   │   └── files-routing.module.ts
│   │
│   └── metrics/
│       ├── components/
│       │   └── grafana-embed/
│       ├── metrics.component.ts
│       └── metrics-routing.module.ts
│
├── layout/                        # Layout components
│   ├── navbar/
│   │   ├── navbar.component.ts
│   │   ├── navbar.component.html
│   │   └── navbar.component.scss
│   ├── footer/
│   │   └── footer.component.ts
│   └── main-layout/
│       └── main-layout.component.ts
│
├── store/                         # Root NgRx store
│   ├── app.state.ts               # Root state interface
│   ├── app.reducer.ts             # Root reducer
│   └── app.effects.ts             # Root effects
│
├── app-routing.module.ts          # Root routing
├── app.component.ts               # Root component
└── app.module.ts                  # Root module
```

### 6.2 Routing Structure

```typescript
const routes: Routes = [
  { path: '', redirectTo: '/dashboard', pathMatch: 'full' },
  {
    path: 'login',
    loadChildren: () => import('./features/auth/auth.module').then(m => m.AuthModule)
  },
  {
    path: '',
    component: MainLayoutComponent,
    canActivate: [AuthGuard],
    children: [
      {
        path: 'dashboard',
        loadChildren: () => import('./features/dashboard/dashboard.module').then(m => m.DashboardModule)
      },
      {
        path: 'service-accounts',
        loadChildren: () => import('./features/service-accounts/service-accounts.module').then(m => m.ServiceAccountsModule)
      },
      {
        path: 'storage-elements',
        loadChildren: () => import('./features/storage-elements/storage-elements.module').then(m => m.StorageElementsModule)
      },
      {
        path: 'files',
        loadChildren: () => import('./features/files/files.module').then(m => m.FilesModule)
      },
      {
        path: 'metrics',
        loadChildren: () => import('./features/metrics/metrics.module').then(m => m.MetricsModule)
      }
    ]
  },
  { path: '**', redirectTo: '/dashboard' }
];
```

### 6.3 State Management (NgRx)

**Root State**:
```typescript
export interface AppState {
  auth: AuthState;
  theme: ThemeState;
  serviceAccounts: ServiceAccountsState;
  storageElements: StorageElementsState;
  files: FilesState;
}
```

**Feature State Examples**:

**ServiceAccountsState**:
```typescript
export interface ServiceAccountsState {
  items: ServiceAccount[];
  selectedItem: ServiceAccount | null;
  loading: boolean;
  error: string | null;
  pagination: {
    total: number;
    page: number;
    limit: number;
  };
  filters: {
    role: string | null;
    status: string | null;
    search: string | null;
  };
}
```

**StorageElementsState**:
```typescript
export interface StorageElementsState {
  items: StorageElement[];
  selectedItem: StorageElement | null;
  loading: boolean;
  error: string | null;
  pagination: {
    total: number;
    page: number;
    limit: number;
  };
  filters: {
    mode: string[];
    storageType: string[];
    search: string | null;
  };
}
```

---

## 7. API Integration Layer

### 7.1 Base API Service

```typescript
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly baseUrl = environment.apiUrl; // http://localhost:8000/api

  constructor(private http: HttpClient) {}

  get<T>(endpoint: string, params?: HttpParams): Observable<T> {
    return this.http.get<T>(`${this.baseUrl}${endpoint}`, { params });
  }

  post<T>(endpoint: string, body: any): Observable<T> {
    return this.http.post<T>(`${this.baseUrl}${endpoint}`, body);
  }

  patch<T>(endpoint: string, body: any): Observable<T> {
    return this.http.patch<T>(`${this.baseUrl}${endpoint}`, body);
  }

  delete<T>(endpoint: string): Observable<T> {
    return this.http.delete<T>(`${this.baseUrl}${endpoint}`);
  }
}
```

### 7.2 JWT Interceptor

```typescript
@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  constructor(private authService: AuthService) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const token = this.authService.getAccessToken();

    if (token) {
      req = req.clone({
        setHeaders: {
          Authorization: `Bearer ${token}`
        }
      });
    }

    return next.handle(req).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 401) {
          // Token expired, try refresh
          return this.authService.refreshToken().pipe(
            switchMap(() => {
              const newToken = this.authService.getAccessToken();
              req = req.clone({
                setHeaders: {
                  Authorization: `Bearer ${newToken}`
                }
              });
              return next.handle(req);
            }),
            catchError(() => {
              // Refresh failed, logout
              this.authService.logout();
              return throwError(() => error);
            })
          );
        }
        return throwError(() => error);
      })
    );
  }
}
```

### 7.3 Feature-specific Services

**ServiceAccountsService**:
```typescript
@Injectable({ providedIn: 'root' })
export class ServiceAccountsService {
  constructor(private api: ApiService) {}

  getList(params: ServiceAccountsListParams): Observable<PaginatedResponse<ServiceAccount>> {
    const httpParams = new HttpParams({ fromObject: params as any });
    return this.api.get<PaginatedResponse<ServiceAccount>>('/service-accounts', httpParams);
  }

  getById(id: string): Observable<ServiceAccount> {
    return this.api.get<ServiceAccount>(`/service-accounts/${id}`);
  }

  create(data: CreateServiceAccountRequest): Observable<ServiceAccount> {
    return this.api.post<ServiceAccount>('/service-accounts', data);
  }

  update(id: string, data: UpdateServiceAccountRequest): Observable<ServiceAccount> {
    return this.api.patch<ServiceAccount>(`/service-accounts/${id}`, data);
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/service-accounts/${id}`);
  }

  rotateSecret(id: string): Observable<RotateSecretResponse> {
    return this.api.post<RotateSecretResponse>(`/service-accounts/${id}/rotate-secret`, {});
  }

  bulkDelete(ids: string[]): Observable<BulkOperationResponse> {
    return this.api.post<BulkOperationResponse>('/service-accounts/bulk/delete', { ids });
  }
}
```

---

## 8. Error Handling Strategy

### 8.1 Global Error Handler

```typescript
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  constructor(
    private injector: Injector,
    private toastService: ToastService
  ) {}

  handleError(error: Error | HttpErrorResponse): void {
    if (error instanceof HttpErrorResponse) {
      // HTTP errors
      this.handleHttpError(error);
    } else {
      // Client-side errors
      this.handleClientError(error);
    }
  }

  private handleHttpError(error: HttpErrorResponse): void {
    const message = this.extractErrorMessage(error);

    switch (error.status) {
      case 400:
        this.toastService.error('Invalid request: ' + message);
        break;
      case 401:
        // Handled by AuthInterceptor
        break;
      case 403:
        this.toastService.error('Access denied');
        break;
      case 404:
        this.toastService.error('Resource not found');
        break;
      case 500:
        this.toastService.error('Server error. Please try again later.');
        break;
      default:
        this.toastService.error('An error occurred: ' + message);
    }
  }

  private handleClientError(error: Error): void {
    console.error('Client error:', error);
    this.toastService.error('An unexpected error occurred');
  }

  private extractErrorMessage(error: HttpErrorResponse): string {
    if (error.error?.message) {
      return error.error.message;
    }
    if (error.error?.detail) {
      return error.error.detail;
    }
    return error.message;
  }
}
```

### 8.2 Component-level Error Handling

**Вопрос для уточнения**: Предпочтение глобальному error handler или дополнительная per-component обработка для специфичных случаев?

**Предложение**: Комбинированный подход:
- **Global Error Handler**: Для общих HTTP ошибок и unexpected errors
- **Component-level**: Для специфичной бизнес-логики (например, validation errors в формах)

---

## 9. Toast Notifications System

### 9.1 Toast Service

```typescript
export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title?: string;
  message: string;
  duration?: number;
  dismissible?: boolean;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private toasts$ = new BehaviorSubject<ToastMessage[]>([]);

  get toasts(): Observable<ToastMessage[]> {
    return this.toasts$.asObservable();
  }

  success(message: string, title?: string, duration = 5000): void {
    if (this.isSuccessNotificationsEnabled()) {
      this.show({ type: 'success', message, title, duration });
    }
  }

  error(message: string, title?: string, duration = 10000): void {
    this.show({ type: 'error', message, title, duration });
  }

  warning(message: string, title?: string, duration = 7000): void {
    this.show({ type: 'warning', message, title, duration });
  }

  info(message: string, title?: string, duration = 5000): void {
    this.show({ type: 'info', message, title, duration });
  }

  private show(toast: Omit<ToastMessage, 'id' | 'dismissible'>): void {
    const id = this.generateId();
    const newToast: ToastMessage = { ...toast, id, dismissible: true };

    this.toasts$.next([...this.toasts$.value, newToast]);

    if (toast.duration) {
      setTimeout(() => this.remove(id), toast.duration);
    }
  }

  remove(id: string): void {
    this.toasts$.next(this.toasts$.value.filter(t => t.id !== id));
  }

  private isSuccessNotificationsEnabled(): boolean {
    // Read from settings (localStorage or NgRx state)
    return localStorage.getItem('showSuccessToasts') !== 'false';
  }

  private generateId(): string {
    return `toast-${Date.now()}-${Math.random()}`;
  }
}
```

### 9.2 Toast Component

**Bootstrap Toast** или **ngx-toastr** library

**Позиция**: Top-right corner (fixed position)

**Auto-dismiss timing**:
- Success: 5 seconds
- Info: 5 seconds
- Warning: 7 seconds
- Error: 10 seconds (или manual dismiss only)

**Settings Toggle**:
- Global setting в user preferences: "Show success notifications" (checkbox)
- Ошибки всегда показываются (нельзя отключить)

---

## 10. Confirmation Modals

### 10.1 Reusable Confirmation Component

```typescript
export interface ConfirmationConfig {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  confirmButtonClass?: string;
  dangerAction?: boolean;
  requireTyping?: string; // "Type DELETE to confirm"
}

@Component({
  selector: 'app-confirmation-modal',
  template: `
    <div class="modal-header">
      <h5>{{ config.title }}</h5>
    </div>
    <div class="modal-body">
      <p [innerHTML]="config.message"></p>
      <div *ngIf="config.requireTyping">
        <label>Type <strong>{{ config.requireTyping }}</strong> to confirm:</label>
        <input
          type="text"
          class="form-control"
          [(ngModel)]="typedText"
          (input)="onTypedTextChange()"
        />
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" (click)="cancel()">
        {{ config.cancelText || 'Cancel' }}
      </button>
      <button
        class="btn"
        [ngClass]="config.confirmButtonClass || 'btn-primary'"
        [disabled]="!canConfirm()"
        (click)="confirm()"
      >
        {{ config.confirmText || 'Confirm' }}
      </button>
    </div>
  `
})
export class ConfirmationModalComponent {
  @Input() config: ConfirmationConfig;
  typedText = '';

  canConfirm(): boolean {
    if (this.config.requireTyping) {
      return this.typedText === this.config.requireTyping;
    }
    return true;
  }

  confirm(): void {
    // Close modal with confirmation
  }

  cancel(): void {
    // Close modal without confirmation
  }
}
```

### 10.2 Usage Examples

**Delete Service Account**:
```typescript
const config: ConfirmationConfig = {
  title: 'Delete Service Account',
  message: `Are you sure you want to delete service account <strong>${account.name}</strong>?<br><br>This action cannot be undone.`,
  confirmText: 'Delete',
  cancelText: 'Cancel',
  confirmButtonClass: 'btn-danger',
  dangerAction: true
};
```

**Change Storage Mode**:
```typescript
const config: ConfirmationConfig = {
  title: 'Change Storage Mode',
  message: `
    ⚠️ WARNING: After changing the mode to <strong>${newMode}</strong>, you MUST:<br><br>
    1. Update the storage-element configuration file<br>
    2. Restart the storage-element service<br><br>
    Mode transition rules:<br>
    - edit → rw: Files can no longer be deleted<br>
    - rw → ro: Files can no longer be added or modified<br>
    - ro → ar: Files metadata only, physical files moved to cold storage<br><br>
    This operation cannot be reversed via UI.
  `,
  confirmText: 'Change Mode',
  cancelText: 'Cancel',
  confirmButtonClass: 'btn-warning'
};
```

**Delete File** (с required typing):
```typescript
const config: ConfirmationConfig = {
  title: 'Delete File',
  message: `
    ⚠️ WARNING: This action cannot be undone.<br><br>
    File: <strong>${file.originalFilename}</strong><br>
    Uploaded by: ${file.username}<br>
    Upload date: ${file.uploadDate}<br><br>
    This will permanently delete:<br>
    - Physical file from storage<br>
    - Attribute file (*.attr.json)<br>
    - Database cache entry
  `,
  confirmText: 'Delete',
  cancelText: 'Cancel',
  confirmButtonClass: 'btn-danger',
  dangerAction: true,
  requireTyping: 'DELETE'
};
```

---

## 11. Implementation Roadmap

### Phase 1: MVP (Weeks 1-4)

**Week 1: Project Setup & Authentication**
- ✅ Angular project initialization (Angular CLI)
- ✅ Bootstrap 5 integration
- ✅ NgRx setup (root store)
- ✅ Routing configuration
- ✅ Theme service (Light/Dark mode)
- ✅ Login page UI
- ✅ Authentication service (JWT tokens)
- ✅ Auth guard & interceptor
- ✅ Layout components (Navbar, Footer, MainLayout)

**Week 2: Dashboard & Service Accounts List**
- ✅ Dashboard page (basic structure)
- ✅ Service Status Grid component (mock data first)
- ✅ Quick Actions component
- ✅ Statistics Overview component
- ✅ Service Accounts list page
- ✅ Service Accounts table component
- ✅ Pagination component
- ✅ NgRx state for Service Accounts

**Week 3: Service Accounts CRUD**
- ✅ Create Service Account form (modal)
- ✅ View Service Account details (modal)
- ✅ Edit Service Account form (modal)
- ✅ Delete Service Account (confirmation modal)
- ✅ Service Accounts API service
- ✅ NgRx effects для Service Accounts
- ✅ Toast notifications integration

**Week 4: Storage Elements List & Details**
- ✅ Storage Elements list page
- ✅ Storage Elements table component
- ✅ Filters component (mode, type, search)
- ✅ View Storage Element details (modal)
- ✅ NgRx state for Storage Elements
- ✅ Storage Elements API service

**Deliverable Phase 1**: Functional admin UI с authentication, dashboard, full Service Accounts management, и read-only Storage Elements

---

### Phase 2: Advanced Features (Weeks 5-8)

**Week 5: Service Accounts Advanced Features**
- ✅ Rotate Secret functionality
- ✅ Bulk operations (delete, role change, enable/disable)
- ✅ Advanced filters (date range, multi-select)
- ✅ Webhooks management UI (будущее, low priority)

**Week 6: Storage Elements CRUD**
- ✅ Create Storage Element form
- ✅ Edit Storage Element form
- ✅ Change Mode functionality (с предупреждениями)
- ✅ Delete Storage Element (confirmation)
- ✅ Validation для S3 credentials и Local paths

**Week 7: Storage Elements Monitoring**
- ✅ Real-time capacity monitoring
- ✅ Alert indicators (retention expiring, capacity warnings)
- ✅ Storage usage charts (Chart.js integration)
- ✅ WebSocket integration для real-time updates (Dashboard)

**Week 8: Testing & Refinement**
- ✅ Unit tests для critical components
- ✅ E2E tests (Cypress или Playwright)
- ✅ Bug fixes
- ✅ Performance optimization

**Deliverable Phase 2**: Полнофункциональное управление Service Accounts и Storage Elements, real-time мониторинг, bulk operations

---

### Phase 3: File Manager & Metrics (Weeks 9-12)

**Week 9: File Manager - Search & List**
- ✅ File search form (по атрибутам)
- ✅ File list table
- ✅ Pagination (настраиваемая)
- ✅ Filters (filename, username, date range, storage element, extension, size)
- ✅ NgRx state для Files

**Week 10: File Manager - Operations**
- ✅ View File Metadata (modal с JSON tree view)
- ✅ Download File functionality
- ✅ Delete File (только edit mode storage, с confirmation)
- ✅ Transfer File (ro → edit storage)
- ✅ Files API service
- ✅ NgRx effects для Files

**Week 11: Metrics & Grafana Integration**
- ✅ Metrics page structure
- ✅ Grafana iframe embed
- ✅ Dashboard selector (multiple dashboards)
- ✅ Theme integration (Light/Dark mode в Grafana)
- ✅ Auto-refresh configuration

**Week 12: Final Polish & Documentation**
- ✅ UI/UX improvements
- ✅ Accessibility testing (keyboard navigation, screen readers)
- ✅ Documentation (README, user guide)
- ✅ Deployment guide (Docker, Nginx)

**Deliverable Phase 3**: Полностью функциональный Admin UI со всеми запланированными features

---

## 12. Backend API Requirements (admin-module)

### 12.1 New Endpoints Required

#### Admin Authentication (NEW)
```http
POST   /api/admin-auth/login
POST   /api/admin-auth/refresh
POST   /api/admin-auth/logout
GET    /api/admin-auth/me
```

#### System Status (NEW)
```http
GET    /api/admin/system/status      # Service health, metrics, alerts
```

#### Service Accounts (EXISTING, возможно нужны улучшения)
```http
GET    /api/service-accounts          # With pagination, filters, search
GET    /api/service-accounts/:id
POST   /api/service-accounts
PATCH  /api/service-accounts/:id
DELETE /api/service-accounts/:id
POST   /api/service-accounts/:id/rotate-secret
POST   /api/service-accounts/bulk/delete
PATCH  /api/service-accounts/bulk/role
PATCH  /api/service-accounts/bulk/status
```

#### Storage Elements (EXISTING, возможно нужны улучшения)
```http
GET    /api/storage-elements          # With pagination, filters, search
GET    /api/storage-elements/:id
POST   /api/storage-elements
PATCH  /api/storage-elements/:id
DELETE /api/storage-elements/:id
POST   /api/storage-elements/:id/change-mode
```

#### Files (NEW, координация с Query Module)
```http
GET    /api/files/search              # Search by attributes
GET    /api/files/:id                 # Metadata
GET    /api/files/:id/download        # Download file
DELETE /api/files/:id                 # Delete (only edit mode)
POST   /api/files/:id/transfer        # Transfer ro → edit
```

### 12.2 Pagination, Filtering, Sorting Standard

**Query Parameters**:
```
?page=1                 # Page number (1-based)
&limit=25               # Items per page
&sort=name              # Sort field
&order=asc              # Sort order (asc/desc)
&search=query           # Global search
&[field]=value          # Field-specific filter
```

**Response Format**:
```json
{
  "items": [ /* array of objects */ ],
  "total": 243,
  "page": 1,
  "limit": 25,
  "pages": 10
}
```

---

## 13. Deployment & Configuration

### 13.1 Environment Configuration

```typescript
// src/environments/environment.ts
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api',
  grafanaUrl: 'http://localhost:3000',
  websocketUrl: 'ws://localhost:8000/ws',
  tokenRefreshInterval: 1500000, // 25 minutes (before 30min expiry)
  toastDuration: {
    success: 5000,
    error: 10000,
    warning: 7000,
    info: 5000
  }
};

// src/environments/environment.prod.ts
export const environment = {
  production: true,
  apiUrl: '/api',  // Relative URL for production
  grafanaUrl: '/grafana',
  websocketUrl: 'wss://artstore.example.com/ws',
  tokenRefreshInterval: 1500000,
  toastDuration: {
    success: 5000,
    error: 10000,
    warning: 7000,
    info: 5000
  }
};
```

### 13.2 Docker Deployment

**Dockerfile**:
```dockerfile
FROM node:20 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build -- --configuration production

FROM nginx:alpine
COPY --from=builder /app/dist/artstore-admin-ui /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**nginx.conf**:
```nginx
server {
  listen 80;
  server_name localhost;
  root /usr/share/nginx/html;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /api/ {
    proxy_pass http://admin-module:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }

  location /grafana/ {
    proxy_pass http://grafana:3000/;
    proxy_set_header Host $host;
  }

  location /ws/ {
    proxy_pass http://admin-module:8000/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
  }
}
```

### 13.3 docker-compose.yml Integration

```yaml
services:
  admin-ui:
    build:
      context: ./admin-ui
      dockerfile: Dockerfile
    ports:
      - "4200:80"
    depends_on:
      - admin-module
    environment:
      - API_URL=http://admin-module:8000/api
      - GRAFANA_URL=http://grafana:3000
    networks:
      - artstore-network
```

---

## 14. Security Considerations

### 14.1 Authentication Security

- **JWT Storage**: localStorage (с XSS protection через CSP headers)
- **Token Expiry**: Access token 30 min, Refresh token 7 days
- **Auto Logout**: При истечении refresh token
- **HTTPS Only**: Production должен использовать HTTPS
- **CORS Configuration**: Backend должен разрешать только trusted origins

### 14.2 XSS Protection

- **Content Security Policy** (CSP headers в nginx):
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' http://localhost:8000 ws://localhost:8000;";
```

- **Angular Sanitization**: Использовать DomSanitizer для динамического HTML
- **Input Validation**: Все user inputs валидируются на client и server side

### 14.3 CSRF Protection

- **CSRF Tokens**: Если backend требует (обычно для cookie-based auth)
- **SameSite Cookies**: `SameSite=Strict` для session cookies (если используются)

### 14.4 Role-Based Access Control (будущее)

- **Frontend Route Guards**: Проверка роли перед доступом к страницам
- **UI Element Hiding**: Скрывать кнопки/actions для unauthorized roles
- **Backend Enforcement**: Основная защита на backend (frontend - только UX)

---

## 15. Testing Strategy

### 15.1 Unit Tests

**Frameworks**: Jasmine + Karma

**Coverage Target**: 70%+ для critical components

**Prioritize Testing**:
- Services (API services, AuthService, ThemeService)
- NgRx reducers, effects, selectors
- Pipes (file-size, time-ago)
- Utilities (validation functions)

**Example**:
```typescript
describe('ServiceAccountsService', () => {
  let service: ServiceAccountsService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ServiceAccountsService, ApiService]
    });
    service = TestBed.inject(ServiceAccountsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('should fetch service accounts list', () => {
    const mockResponse = { items: [], total: 0, page: 1, limit: 25 };

    service.getList({ page: 1, limit: 25 }).subscribe(response => {
      expect(response).toEqual(mockResponse);
    });

    const req = httpMock.expectOne('/api/service-accounts?page=1&limit=25');
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);
  });
});
```

### 15.2 Integration Tests / E2E Tests

**Framework**: Playwright или Cypress

**Critical User Flows**:
1. **Login Flow**: Login → Dashboard → Logout
2. **Service Account CRUD**: Create → View → Edit → Delete
3. **Storage Element Management**: Create → Change Mode → Delete
4. **File Operations**: Search → View Metadata → Download → Delete

**Example (Playwright)**:
```typescript
test('should create a new service account', async ({ page }) => {
  await page.goto('http://localhost:4200/login');
  await page.fill('input[name="username"]', 'admin');
  await page.fill('input[name="password"]', 'password');
  await page.click('button[type="submit"]');

  await page.waitForURL('**/dashboard');
  await page.click('a[href="/service-accounts"]');
  await page.click('button:has-text("Create Service Account")');

  await page.fill('input[name="name"]', 'Test Account');
  await page.fill('input[name="client_id"]', 'test-client-id');
  await page.fill('input[name="client_secret"]', 'very-secure-secret-32-chars-min');
  await page.selectOption('select[name="role"]', 'USER');
  await page.click('button:has-text("Create")');

  await expect(page.locator('text=Service account created successfully')).toBeVisible();
  await expect(page.locator('text=Test Account')).toBeVisible();
});
```

### 15.3 Performance Testing

**Metrics to Monitor**:
- Initial Load Time (< 3 seconds)
- Time to Interactive (< 5 seconds)
- Lighthouse Score (>90 for Performance, Accessibility)
- Bundle Size (< 500KB initial, < 2MB total)

**Tools**:
- Chrome DevTools Lighthouse
- webpack-bundle-analyzer
- Angular CLI build analyzer

---

## 16. Accessibility (a11y)

### 16.1 WCAG 2.1 Level AA Compliance

**Key Requirements**:
- ✅ Keyboard navigation (Tab, Enter, Escape)
- ✅ ARIA labels для screen readers
- ✅ Color contrast ratio ≥ 4.5:1 для текста
- ✅ Focus indicators visible
- ✅ Form validation messages accessible
- ✅ Modal dialogs trap focus

**Bootstrap Accessibility**:
- Bootstrap 5 компоненты уже имеют basic a11y support
- Дополнительные ARIA attributes где нужно

### 16.2 Keyboard Shortcuts (будущее)

- `Ctrl+/` - Show keyboard shortcuts help
- `Ctrl+K` - Focus global search
- `Esc` - Close modal/dropdown
- `Tab` / `Shift+Tab` - Navigate between focusable elements
- `Enter` / `Space` - Activate buttons/links

---

## 17. Internationalization (i18n) - Будущее

**На начальном этапе**: Только русский язык (hardcoded strings)

**Будущее расширение**:
- Angular i18n для multi-language support
- Языки: Русский (ru), English (en)
- Переключатель языка в navbar

---

## 18. Browser Support

**Officially Supported**:
- ✅ Chrome (last 2 versions)
- ✅ Firefox (last 2 versions)
- ✅ Edge (last 2 versions)

**Not Supported**:
- ❌ Internet Explorer
- ❌ Safari (не тестируется, но скорее всего работает)
- ❌ Mobile browsers (не оптимизируется)

**Polyfills**: Минимальные (Angular включает необходимые)

---

## 19. Performance Optimization

### 19.1 Bundle Optimization

- **Lazy Loading**: Все feature modules загружаются по требованию
- **Tree Shaking**: Удаление неиспользуемого кода
- **Code Splitting**: Vendor, polyfills, app code раздельно
- **Compression**: Gzip/Brotli на nginx

### 19.2 Runtime Optimization

- **OnPush Change Detection**: Для всех компонентов с immutable data (NgRx)
- **TrackBy Functions**: Для всех *ngFor с динамическими списками
- **Virtual Scrolling** (будущее): Для больших таблиц (>1000 rows)
- **Debouncing**: Для search inputs, filters

### 19.3 Caching Strategy

- **HTTP Caching**: Cache API responses где возможно
- **LocalStorage**: Кеширование user preferences, theme
- **Service Worker** (будущее): Offline caching для static assets

---

## 20. Open Questions & Decisions Needed

### 20.1 Service Accounts

**Q1**: Rotate Secret - автоматическая генерация или ручной ввод нового секрета?
- **Предложение**: Автоматическая генерация (более безопасно)

**Q2**: Webhooks management - какие именно события поддерживать?
- **Предложение**: file_restored, restore_failed, file_expiring (из документации)

**Q3**: Service Accounts activity log - детализация?
- **Предложение**: Phase 3 feature, показывать last 10 API calls

### 20.2 Storage Elements

**Q4**: Test Connection при создании storage element - обязательно или optional?
- **Предложение**: Optional, но рекомендуется (кнопка "Test Connection")

**Q5**: Storage Element deletion - какие ограничения?
- **Предложение**: Нельзя удалить если есть файлы (показать ошибку с количеством файлов)

### 20.3 Files

**Q6**: File preview - нужен ли в будущем?
- **Спецификация**: Нет (по требованиям)

**Q7**: File transfer - только ro → edit или другие варианты?
- **Спецификация**: Только ro → edit (подтверждено)

**Q8**: Batch file operations (bulk delete, bulk transfer)?
- **Предложение**: Phase 3 feature если потребуется

### 20.4 General

**Q9**: Error handling - глобальный handler или per-component?
- **Предложение**: Комбинированный (глобальный + специфичная обработка в компонентах)

**Q10**: Real-time updates - WebSocket или polling?
- **Предложение**: WebSocket для dashboard status, polling для остального (каждые 30-60 сек)

**Q11**: Admin users management - когда реализовывать?
- **Предложение**: Phase 2-3, начать с single hardcoded admin account

---

## 21. Appendix

### 21.1 Color Palette (Detailed)

```scss
// Primary (Салатовый)
$lime-50:  #F9FBE7;
$lime-100: #F0F4C3;
$lime-200: #E6EE9C;
$lime-300: #DCE775;
$lime-400: #D4E157;
$lime-500: #CDDC39;  // Primary
$lime-600: #C0CA33;
$lime-700: #A3D977;  // Main Primary
$lime-800: #8BC34A;  // Primary Dark
$lime-900: #689F38;

// Status Colors
$success: #81C784;   // Светло-зеленый
$info:    #64B5F6;   // Светло-голубой
$warning: #FFD54F;   // Светло-желтый
$danger:  #E57373;   // Светло-красный

// Neutrals (Light Theme)
$gray-50:  #FAFAFA;
$gray-100: #F5F5F5;
$gray-200: #EEEEEE;
$gray-300: #E0E0E0;
$gray-400: #BDBDBD;
$gray-500: #9E9E9E;
$gray-600: #757575;
$gray-700: #616161;
$gray-800: #424242;
$gray-900: #212121;

// Dark Theme
$dark-bg-primary:   #263238;
$dark-bg-secondary: #37474F;
$dark-text-primary: #FFFFFF;
$dark-text-secondary: #B0BEC5;
```

### 21.2 Typography Scale

```scss
$font-family-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
$font-family-mono: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;

$font-size-xs:   0.75rem;  // 12px
$font-size-sm:   0.875rem; // 14px
$font-size-base: 1rem;     // 16px
$font-size-lg:   1.125rem; // 18px
$font-size-xl:   1.25rem;  // 20px
$font-size-2xl:  1.5rem;   // 24px
$font-size-3xl:  1.875rem; // 30px
$font-size-4xl:  2.25rem;  // 36px

$font-weight-light:   300;
$font-weight-normal:  400;
$font-weight-medium:  500;
$font-weight-semibold: 600;
$font-weight-bold:    700;
```

### 21.3 Spacing Scale

```scss
$spacer: 1rem; // 16px

$spacers: (
  0: 0,
  1: $spacer * 0.25,  // 4px
  2: $spacer * 0.5,   // 8px
  3: $spacer,         // 16px
  4: $spacer * 1.5,   // 24px
  5: $spacer * 3,     // 48px
  6: $spacer * 4,     // 64px
  7: $spacer * 6,     // 96px
);
```

### 21.4 Useful Links

- **Angular Documentation**: https://angular.io/docs
- **Bootstrap 5 Documentation**: https://getbootstrap.com/docs/5.3/
- **NgRx Documentation**: https://ngrx.io/docs
- **Chart.js Documentation**: https://www.chartjs.org/docs/
- **Playwright Testing**: https://playwright.dev/
- **WCAG 2.1 Guidelines**: https://www.w3.org/WAI/WCAG21/quickref/

---

## Changelog

**v1.0** (2025-11-17)
- Initial specification based on brainstorming session
- Comprehensive UI/UX design
- Technical architecture defined
- Implementation roadmap created

---

**Конец документа**

Этот документ является живым и будет обновляться по мере развития проекта и получения обратной связи.
