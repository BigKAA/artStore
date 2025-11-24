# Admin UI - Административный интерфейс ArtStore

## Назначение модуля

**Admin UI** — это Angular-based графический интерфейс для администрирования системы ArtStore, обеспечивающий:
- **User-friendly dashboard** с системной статистикой и метриками
- **Service Account Management** (CRUD операции, secret rotation)
- **Storage Element Monitoring** (статус, заполненность, режимы работы)
- **File Manager** с поиском, фильтрацией и просмотром метаданных
- **Audit Logs Viewer** для отслеживания всех операций в системе

## Ключевые возможности

### 1. Dashboard

#### System Overview
- **Total Storage**: Общий объем хранилища и использование
- **File Statistics**: Количество файлов, средний размер, распределение по типам
- **Storage Elements Health**: Статус всех элементов хранения
- **Recent Activity**: Последние uploads, downloads, deletions

#### Metrics Visualization
- **Upload/Download Trends**: Графики загрузки и скачивания за период
- **Storage Utilization**: Динамика заполнения Storage Elements
- **Performance Metrics**: Latency, throughput, error rates
- **User Activity**: Топ пользователей по активности

### 2. Service Account Management

#### CRUD Operations
- **Create Service Account**: Генерация client_id и client_secret
- **List Service Accounts**: С фильтрацией по role, status
- **Edit Service Account**: Обновление permissions, rate limits
- **Delete Service Account**: С подтверждением (защита is_system accounts)

#### Security Features
- **Secret Rotation**: Manual rotation с copy-to-clipboard новых credentials
- **Status Management**: Suspend/Activate accounts
- **Permission Management**: Fine-grained resource-level permissions
- **Audit Trail**: История всех изменений Service Account

### 3. Storage Element Management

#### Monitoring
- **List Storage Elements**: С real-time статусами
- **Element Details**: Конфигурация, статистика, health checks
- **Mode Visualization**: Color-coded режимы (edit=green, rw=blue, ro=yellow, ar=gray)
- **Space Utilization**: Progress bars для visualize заполненности

#### Configuration
- **Register Storage Element**: Добавление нового элемента
- **Update Configuration**: Изменение max_size, retention_days
- **Mode Transition**: rw → ro, ro → ar с confirmation dialogs
- **Delete Element**: С проверкой отсутствия файлов

### 4. File Manager

#### Search & Browse
- **Full-text Search**: Интеграция с Query Module search API
- **Advanced Filters**: По MIME type, size, date range, Storage Element
- **Pagination**: Efficient pagination для больших результатов
- **Sort Options**: По filename, size, upload date

#### File Operations
- **View Metadata**: Modal с полными attr.json данными
- **Download File**: Direct download через Query Module API
- **Delete File**: С confirmation (только для edit mode files)
- **Transfer File**: Между Storage Elements с progress tracking

#### Batch Operations
- **Bulk Delete**: Multi-select с batch deletion
- **Bulk Transfer**: Перенос множественных файлов
- **Export Metadata**: CSV/JSON export выбранных файлов

### 5. Audit Logs

#### Log Viewer
- **Real-time Updates**: WebSocket connection для live logs
- **Filtering**: По event type, user, date range, resource
- **Search**: Full-text search по log messages
- **Export**: CSV/JSON export для external analysis

#### Event Types
- `service_account_created`, `service_account_deleted`
- `file_uploaded`, `file_downloaded`, `file_deleted`
- `storage_element_added`, `storage_mode_changed`
- `auth_success`, `auth_failure`

## Технологический стек

### Frontend Framework
- **Angular 17+** с standalone components
- **TypeScript** для type-safe development
- **RxJS** для reactive programming

### UI Components
- **Angular Material** для Material Design components
- **Chart.js / ApexCharts** для визуализации метрик
- **AG-Grid** для advanced data tables (опционально)

### State Management
- **NgRx** для state management (опционально)
- **Services** с RxJS BehaviorSubject для simple state

### HTTP & API
- **HttpClient** для REST API calls к Admin Module и Query Module
- **WebSocket** для real-time updates (audit logs, metrics)
- **Interceptors**: Automatic JWT token injection, error handling

### Build & Deployment
- **Angular CLI** для build и development
- **Nginx** для production serving
- **Docker** для containerization

## Архитектура приложения

```
admin-ui/
├── src/
│   ├── app/
│   │   ├── core/                    # Core services, guards, interceptors
│   │   │   ├── services/
│   │   │   │   ├── auth.service.ts  # JWT authentication
│   │   │   │   ├── api.service.ts   # HTTP client wrapper
│   │   │   │   └── websocket.service.ts
│   │   │   ├── guards/
│   │   │   │   └── auth.guard.ts    # Route protection
│   │   │   └── interceptors/
│   │   │       ├── auth.interceptor.ts    # JWT injection
│   │   │       └── error.interceptor.ts   # Global error handling
│   │   │
│   │   ├── shared/                  # Shared components, directives, pipes
│   │   │   ├── components/
│   │   │   │   ├── file-size.pipe.ts
│   │   │   │   └── date-format.pipe.ts
│   │   │   └── models/
│   │   │       ├── service-account.model.ts
│   │   │       ├── storage-element.model.ts
│   │   │       └── file.model.ts
│   │   │
│   │   ├── features/                # Feature modules
│   │   │   ├── dashboard/
│   │   │   │   ├── dashboard.component.ts
│   │   │   │   ├── dashboard.component.html
│   │   │   │   └── dashboard.component.scss
│   │   │   ├── service-accounts/
│   │   │   │   ├── service-accounts-list/
│   │   │   │   ├── service-account-detail/
│   │   │   │   └── service-account-create/
│   │   │   ├── storage-elements/
│   │   │   │   ├── storage-elements-list/
│   │   │   │   └── storage-element-detail/
│   │   │   ├── file-manager/
│   │   │   │   ├── file-search/
│   │   │   │   ├── file-list/
│   │   │   │   └── file-detail/
│   │   │   ├── audit-logs/
│   │   │   │   └── audit-logs-viewer/
│   │   │   └── auth/
│   │   │       ├── login/
│   │   │       └── logout/
│   │   │
│   │   ├── app.component.ts         # Root component
│   │   ├── app.routes.ts            # Route configuration
│   │   └── app.config.ts            # App configuration
│   │
│   ├── assets/                      # Static assets
│   ├── environments/                # Environment configs
│   │   ├── environment.ts           # Development
│   │   └── environment.prod.ts      # Production
│   ├── index.html
│   └── main.ts
│
├── angular.json                     # Angular CLI configuration
├── package.json                     # NPM dependencies
├── tsconfig.json                    # TypeScript configuration
├── Dockerfile                       # Production Docker image
└── nginx.conf                       # Nginx configuration для production
```

## Конфигурация

### Environment Variables (Angular)

**src/environments/environment.ts** (Development):
```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api',  # Admin Module API
  queryApiUrl: 'http://localhost:8030/api',  # Query Module API
  websocketUrl: 'ws://localhost:8000/ws',
  version: '1.0.0'
};
```

**src/environments/environment.prod.ts** (Production):
```typescript
export const environment = {
  production: true,
  apiUrl: 'https://api.artstore.example.com/api',
  queryApiUrl: 'https://query.artstore.example.com/api',
  websocketUrl: 'wss://api.artstore.example.com/ws',
  version: '1.0.0'
};
```

### Nginx Configuration (Production)

```nginx
server {
    listen 80;
    server_name admin.artstore.example.com;

    root /usr/share/nginx/html;
    index index.html;

    # Angular routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy (опционально)
    location /api/ {
        proxy_pass http://admin-module:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket proxy
    location /ws {
        proxy_pass http://admin-module:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";
}
```

## Development

### Local Development

```bash
# Install dependencies
cd admin-ui
npm install

# Start development server
npm start
# или
ng serve

# Navigate to http://localhost:4200
```

### Build

```bash
# Development build
ng build

# Production build
ng build --configuration=production

# Output: dist/admin-ui/
```

### Docker

```bash
# Build production Docker image
docker build -t artstore-admin-ui:latest .

# Run
docker run -d -p 4200:80 artstore-admin-ui:latest
```

## Тестирование

### Unit Tests (Jasmine + Karma)

```bash
# Run unit tests
ng test

# Coverage report
ng test --code-coverage
```

### E2E Tests (Cypress/Playwright)

```bash
# Run E2E tests
npm run e2e

# Interactive mode
npm run e2e:open
```

## Security Considerations

### Authentication Flow

1. **Login**: POST `/api/auth/token` с client_id/client_secret
2. **Store JWT**: В sessionStorage (не localStorage для security)
3. **Auto-inject**: JWT в Authorization header через interceptor
4. **Auto-refresh**: Refresh token перед expiration
5. **Logout**: Clear sessionStorage и redirect на login

### Security Best Practices

- **No credentials in code**: Используйте environment variables
- **XSS Protection**: Angular sanitization enabled by default
- **CSRF Protection**: CSRF tokens для state-changing operations
- **Secure Communication**: HTTPS only в production
- **Content Security Policy**: Restrictive CSP headers
- **Audit Logging**: Логирование всех административных действий

## Deployment

### Production Checklist

- [ ] Build с `--configuration=production`
- [ ] Enable HTTPS (SSL/TLS certificates)
- [ ] Configure CSP headers в Nginx
- [ ] Set up error monitoring (Sentry, Rollbar)
- [ ] Enable web analytics (Google Analytics, Matomo)
- [ ] Configure rate limiting в Nginx
- [ ] Set up automated backups

### Docker Compose

```yaml
# В корневом docker-compose.yml
admin-ui:
  build: ./admin-ui
  ports:
    - "4200:80"
  environment:
    - API_URL=http://admin-module:8000/api
    - QUERY_API_URL=http://query-module:8030/api
  depends_on:
    - admin-module
    - query-module
```

## Troubleshooting

### Проблемы с API

**Проблема**: CORS errors
**Решение**: Настроить CORS в Admin Module и Query Module для разрешения requests от Admin UI origin.

**Проблема**: 401 Unauthorized
**Решение**: Проверить JWT token не expired. Проверить interceptor корректно добавляет Authorization header.

### Проблемы с производительностью

**Проблема**: Медленная загрузка списков
**Решение**: Реализовать pagination, virtual scrolling для больших списков. Enable lazy loading для feature modules.

## Ссылки на документацию

- [Главная документация проекта](../README.md)
- [Admin Module API](../admin-module/README.md)
- [Query Module API](../query-module/README.md)
- [Storage Element Module API](../storage-element/README.md)
- [Angular Documentation](https://angular.io/docs)
- [Angular Material](https://material.angular.io/)
