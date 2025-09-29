# ArtStore Admin Module

Модуль администратора для системы распределенного файлового хранилища ArtStore.

## Функциональность

### Высокая доступность и отказоустойчивость
- **Raft Consensus Cluster**: Распределенное лидерство с автоматическими выборами в кластере из 3+ узлов
- **Multi-Master Active-Active**: Consistent hashing для распределения нагрузки между всеми узлами
- **Automatic Leader Election**: Переизбрание лидера за < 15 секунд при недоступности текущего
- **Split-Brain Protection**: Кворумные решения предотвращают разделение кластера
- **Zero-Downtime Deployment**: Rolling updates без прерывания сервиса

### Основная функциональность
- **Центр аутентификации**: Генерация JWT-токенов, подписанных по асимметричному алгоритму **RS256**.
- **Saga Orchestrator**: Координация распределенных транзакций для обеспечения консистентности данных.
- **Vector Clock Manager**: Управление глобальным упорядочиванием событий в системе.
- **Conflict Resolution Engine**: Автоматическое разрешение конфликтов данных между storage-element.
- **Управление пользователями**: CRUD операции для пользователей и групп.
- **Управление элементами хранения**: CRUD операции для `storage-element`.
- **Service Discovery**: Публикация конфигурации и состояния `storage-element` в **Redis Sentinel Cluster**.
- **Мониторинг системы**: Health checks, метрики Prometheus, статус системы.
- **Web интерфейс**: Angular, Bootstrap UI для администрирования.

### Комплексная система безопасности

#### Automated JWT Key Rotation
- **Автоматическая ротация ключей**: Ротация RS256 ключевых пар каждые 24 часа с горячей сменой без прерывания сервиса
- **Key Versioning**: Поддержка множественных версий ключей для плавного перехода
- **Grace Period**: 48-часовой период перехода для старых токенов
- **Key Distribution**: Автоматическое распространение новых публичных ключей на все модули через Redis Sentinel

#### Fine-grained RBAC (Role-Based Access Control)
- **Resource-level Permissions**: Контроль доступа на уровне отдельных файлов и storage-element
- **Dynamic Role Assignment**: Назначение ролей на основе атрибутов пользователя и контекста
- **Permission Inheritance**: Иерархическая система наследования прав доступа
- **Temporary Permissions**: Временные права доступа с автоматическим истечением срока

#### Comprehensive Audit Logging
- **Tamper-proof Storage**: Все логи аудита подписываются цифровой подписью для предотвращения изменений
- **Complete Access Trail**: Логирование всех операций доступа с детализацией пользователя, ресурса и действия
- **Structured Logging**: JSON формат с стандартизированными полями для автоматического анализа
- **Real-time Monitoring**: Уведомления о подозрительной активности и нарушениях безопасности

#### Secure Key Management
- **Secure Key Storage**: Защищенное хранение JWT ключей в кластере Admin Module
- **Key Backup**: Резервное копирование ключей между узлами кластера
- **Cryptographic Standards**: Использование проверенных алгоритмов RS256 для JWT подписи
- **Key Security**: Ключи хранятся в зашифрованном виде в защищенной конфигурации

### Advanced Monitoring и Observability

#### OpenTelemetry Distributed Tracing
- **Trace Correlation**: Каждый запрос получает уникальный trace ID для отслеживания через все микросервисы
- **Span Instrumentation**: Автоматическое создание spans для всех HTTP запросов, database queries и Redis операций
- **Context Propagation**: Передача trace контекста через headers во все downstream сервисы
- **Performance Profiling**: Детальное профилирование времени выполнения критических операций

#### Custom Business Metrics
- **Authentication Performance**: Метрики времени валидации JWT токенов и частоты успешных/неуспешных аутентификаций
- **User Management Metrics**: Статистика создания пользователей, изменения ролей и активности администраторов
- **Storage Element Health**: Мониторинг состояния всех подключенных storage-element и их доступности
- **Cluster Coordination**: Метрики Raft consensus, leader elections и split-brain защиты

#### Third-party Analytics Integration
- **Metrics Export**: Экспорт authentication metrics в Prometheus для external analytics
- **Log Aggregation**: Structured logging для integration с ELK Stack, Splunk, DataDog
- **Trace Export**: OpenTelemetry traces для external APM системы (Jaeger, Zipkin, New Relic)


## Запуск и отладка

### Запуск через Docker Compose

Согласно принятой в проекте методологии, запуск приложения осуществляется через `docker-compose-app.yml` в корне проекта.

1.  **Запустите базовую инфраструктуру** (если она еще не запущена):
    ```bash
    # В корне проекта
    docker-compose up -d
    ```

2.  **Соберите и запустите контейнер приложения**:
    ```bash
    # В корне проекта
    docker-compose -f docker-compose-app.yml up --build -d
    ```

Приложение будет доступно по адресу: <http://localhost:8000>

### Локальная разработка (альтернативный способ)

Для отладки можно запустить приложение локально, но **предпочтительным является запуск в Docker**.

1.  **Установите зависимости**:
    ```bash
    # В директории admin-module
    py -m pip install -r requirements.txt
    ```

2.  **Запустите приложение с автоперезагрузкой**:
    ```bash
    # В директории admin-module
    py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```

```bash

## API Эндпоинты

### Аутентификация (`/api/auth`)

- `POST /api/auth/login` - Вход в систему
- `POST /api/auth/logout` - Выход из системы
- `POST /api/auth/refresh` - Обновление access токена
- `GET /api/auth/me` - Информация о текущем пользователе
- `PUT /api/auth/me/password` - Смена пароля текущего пользователя
- `GET /api/auth/validate` - Проверка действительности токена
- `GET /api/auth/status` - Статус службы аутентификации
- `GET /api/auth/health` - Health check для сервиса аутентификации

### Управление пользователями (`/api/users`)

- `GET /api/users/` - Список пользователей с фильтрацией и пагинацией
- `POST /api/users/` - Создание нового пользователя
- `GET /api/users/{user_id}` - Информация о конкретном пользователе
- `PUT /api/users/{user_id}` - Обновление данных пользователя
- `DELETE /api/users/{user_id}` - Удаление пользователя
- `PUT /api/users/{user_id}/password` - Сброс пароля пользователя администратором
- `POST /api/users/{user_id}/activate` - Активация пользователя
- `POST /api/users/{user_id}/deactivate` - Деактивация пользователя
- `POST /api/users/{user_id}/make-admin` - Назначение администратором
- `POST /api/users/{user_id}/remove-admin` - Снятие прав администратора
- `GET /api/users/search/{query}` - Быстрый поиск пользователей
- `GET /api/users/stats/summary` - Статистика пользователей
- `GET /api/users/stats/summary/activity` - Статистика активности пользователей

### Управление элементами хранения (`/api/storage-elements`)

- `POST /api/storage-elements/` - Создание элемента хранения
- `GET /api/storage-elements/` - Список элементов хранения
- `GET /api/storage-elements/stats` - Общая статистика по элементам хранения
- `GET /api/storage-elements/{storage_id}` - Информация об элементе по ID
- `PUT /api/storage-elements/{storage_id}` - Обновление элемента хранения
- `DELETE /api/storage-elements/{storage_id}` - Удаление элемента хранения
- `POST /api/storage-elements/{storage_id}/health` - Проверка здоровья элемента хранения
- `GET /api/storage-elements/{storage_id}/statistics` - Статистика элемента хранения
- `GET /api/storage-elements/{storage_id}/files` - Список файлов из элемента хранения
- `GET /api/storage-elements/retention-warnings` - Элементы с предупреждениями о сроке хранения
- `GET /api/storage-elements/retention-expired` - Элементы с истекшим сроком хранения

### Управление транзакциями (`/api/transactions`)

- `POST /api/transactions/saga/start` - Запуск новой Saga транзакции
- `GET /api/transactions/saga/{saga_id}` - Статус выполнения Saga
- `POST /api/transactions/saga/{saga_id}/compensate` - Принудительная компенсация Saga
- `GET /api/transactions/vector-clock` - Получение текущего Vector Clock
- `POST /api/transactions/vector-clock/sync` - Синхронизация Vector Clock между узлами
- `GET /api/transactions/conflicts` - Список активных конфликтов данных
- `POST /api/transactions/conflicts/{conflict_id}/resolve` - Разрешение конфликта данных

### Администрирование (`/api/admin`)

- `GET /api/admin/system/status` - Статус системы
- `GET /api/admin/system/info` - Информация о системе

### Health Checks и Метрики

- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe
- `GET /health/health` - Детальная проверка здоровья
- `GET /metrics` - Метрики Prometheus
- `GET /` - Корневая страница с информацией о сервисе

## Конфигурация

Конфигурация определяется в файле `config.yaml` и может быть переопределена переменными окружения.

### Пример конфигурации (`config.yaml`)

```yaml
# Настройки сервера
server:
  host: "0.0.0.0"
  port: 8000
  debug: true
  cors_origins: 
    - "http://localhost:3000"
    - "http://localhost:4200"

# База данных
database:
  url: "postgresql+asyncpg://artstore:password@localhost:5432/admin_module"
  user: "artstore"
  user_password: "password"
  pool_size: 10
  max_overflow: 20

# Redis Sentinel Cluster
redis:
  # Список Redis Sentinel endpoints для высокой доступности
  sentinel_hosts:
    - host: "redis-sentinel-1"
      port: 26379
    - host: "redis-sentinel-2"
      port: 26379
    - host: "redis-sentinel-3"
      port: 26379
  master_name: "artstore-master"
  db: 0

  # Fallback конфигурация при недоступности Redis Sentinel
  fallback:
    enabled: true
    config_file: "/app/config/local-fallback.yaml"

# Аутентификация
auth:
  # Локальная система
  local:
    secret_key: "your-secret-key-here-change-in-production"
    algorithm: "HS256"
    access_token_expire_minutes: 30
    refresh_token_expire_days: 7
    # Пользователь администратора по умолчанию при первом запуске модуля.
    default_admin:
      username: "admin"
      email: "admin@artstore.local"
      password: "admin123"
      full_name: "Системный администратор"
      description: "Пользователь администратора системы по умолчанию"
  
# Логирование
logging:
  level: "INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json" # json, text
  
  # Назначения для логов
  handlers:
    console:
      enabled: true
    file:
      enabled: false
      path: "/app/logs/storage-element.log"
      max_bytes: 104857600 # 100MB
      backup_count: 5
    network:
      enabled: false
      protocol: "syslog" # syslog, http
      host: "log-server"
      port: 514

# Настройки метрик Prometheus
metrics:
  enabled: true
  path: "/metrics"
```

## Безопасность

### Аутентификация и Авторизация

Система использует гибридную модель, разделяя внешнюю аутентификацию и внутреннюю авторизацию.

- **Асимметричные JWT (RS256)**: Для внутренней авторизации между сервисами используются JWT-токены, подписанные по алгоритму RS256. Это позволяет каждому сервису проверять подлинность токена локально с помощью общего публичного ключа.

- **Центр Аутентификации**: `Admin Module` является единым центром аутентификации и отвечает за:
    1.  **Проверку учетных данных** пользователя через настроенного провайдера (локальная база, LDAP, OAuth2).
    2.  **Выпуск внутреннего JWT-токена** после успешной внешней аутентификации. В токен включаются данные о пользователе (ID, роли).
    3.  **Управление жизненным циклом токенов** (выпуск, обновление через refresh-токены).

- **Интеграция с LDAP/OAuth2**:
    - Только `Admin Module` напрямую взаимодействует с внешними провайдерами (LDAP/OAuth2).
    - Остальные сервисы системы (`ingester`, `query`, `storage-element`) ничего не знают о внешних провайдерах и работают исключительно с внутренними JWT-токенами.

- **Локальная авторизация**: Валидация токенов (проверка подписи, срока действия) происходит на стороне каждого сервиса. Обращение к `admin-module` для проверки каждого запроса не требуется.

### Защита данных

- Пароли хешируются с использованием bcrypt
- Пароли и секреты маскируются в логах и API ответах
- Системный администратор защищен от случайного удаления

### Использование Bearer токенов

Все запросы к защищенным endpoints должны содержать заголовок авторизации:

```bash
Authorization: Bearer <access_token>
```

**Пример запроса с токеном:**

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
     http://localhost:8000/api/auth/me
```

### Системный администратор

- Создается автоматически при первом запуске из конфигурации
- **Не может быть удален** через API
- **Нельзя убрать права администратора**
- **Нельзя деактивировать**
- Можно изменить только пароль и описание
- По умолчанию: `admin` / `admin123` (обязательно измените в продакшене!)

### Рекомендации по безопасности

1. **Измените пароль администратора по умолчанию** в продакшене
2. **Используйте сильный секретный ключ** для JWT токенов
3. **Настройте HTTPS** для защиты токенов при передаче
4. **Регулярно ротируйте секретные ключи**
5. **Мониторьте неудачные попытки входа**
6. **Используйте короткое время жизни токенов** (30 минут для access, 7 дней для refresh)

## Примеры использования

### Базовая аутентификация

1. **Вход в систему:**

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

2. **Получение информации о текущем пользователе:**

```bash
curl -H "Authorization: Bearer <access_token>" \
     http://localhost:8000/api/auth/me
```

3. **Обновление токена:**

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "<refresh_token>"
  }'
```

### Управление пользователями

1. **Получение списка пользователей:**

```bash
curl -H "Authorization: Bearer <access_token>" \
     "http://localhost:8000/api/users/?page=1&size=10&search=admin"
```

2. **Создание нового пользователя:**

```bash
curl -X POST http://localhost:8000/api/users/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "email": "user@example.com", 
    "password": "secure_password",
    "full_name": "Новый пользователь",
    "is_admin": false
  }'
```

3. **Активация пользователя:**

```bash
curl -X POST http://localhost:8000/api/users/{user_id}/activate \
  -H "Authorization: Bearer <access_token>"
```

4. **Смена пароля администратором:**

```bash
curl -X PUT http://localhost:8000/api/users/{user_id}/password \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "new_password": "new_secure_password"
  }'
```

### Проверка статуса системы

1. **Health checks:**

```bash
# Liveness probe
curl http://localhost:8000/health/live

# Readiness probe  
curl http://localhost:8000/health/ready

# Детальная проверка
curl http://localhost:8000/health/health
```

2. **Метрики Prometheus:**

```bash
curl http://localhost:8000/metrics
```

## Режимы работы элементов хранения

- **EDIT** - Чтение, запись и удаление файлов.
- **RW (Read-Write)** - Чтение и запись файлов. Удаление запрещено.
- **RO (Read-Only)** - Только чтение файлов.
- **COLD (Archive)** - Архивный режим, доступны только метаданные файлов.

Переходы между режимами:

- `edit` - режим менять нельзя.
- `rw` -> `ro` - через API storage_element
- `ro` -> `cold` - через API storage_element
- `cold` → другие режимы - только через перезапуск с изменением конфигурации.

## Мониторинг

Приложение должно отдать метрики мониторинга в формате Prometheus.
Метрики должны содержать следующие данные:

- `up` = 1 Если приложение работает.
- `ready` = 1 Если приложение работает и готово принимать запросы по сети и есть подключение к базе данных
- Информацию о сетевых запросах к API приложения.
- Состояние подключения к базе данных. Если используется connection pool, его состояние.
- Количество и состояние storage_elements.

## Логирование

- Поддержка JSON и текстового формата
- Настраиваемые уровни логирования
- Ротация файлов логов
- Структурированное логирование операций

В конфигурации приложения можно указывать:

- куда сохранять логи приложения:
  - stdout и stderr (по умолчанию).
  - файлы на диске.
  - по сети (смотри какие протоколы для приема логов могут использовать приложения типа flunetbit или vector)
  - логи можно одновременно сохранять как на stdout и stderr, так и в файл.
- уровень важности логов.
- формат логов: txt или json. По умолчанию json.

## Технологии

- Язык программирования: Python >=3.12
- Библиотеки: SQLAlchemy (async mode), FastAPI
- База данных: PostgreSQL >=15
- Кеш: Redis (синхронное соединение).
- UI: Bootstrap 5
- Docker.

## Разработка

Для разработки рекомендуется:

- Использовать виртуальное Python в Docker контейнере
- Запускать инфраструктуру через docker-compose
