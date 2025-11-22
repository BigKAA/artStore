# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ArtStore - это распределенная система файлового хранилища с микросервисной архитектурой, предназначенная для долгосрочного хранения документов с различными сроками хранения. Система реализует принципы отказоустойчивости, горизонтального масштабирования и обеспечивает разделение оперативного и архивного хранения.

## 📚 Документация проекта

**Для новой команды разработки**:
- **`README-PROJECT.md`** - Полное описание проекта, архитектура, технологии, roadmap
- **`DEVELOPMENT-GUIDE.md`** - Руководство по разработке, тестированию, Git workflow
- **Модульные README-PROJECT.md** - Детальное описание каждого модуля в их директориях

**Техническая документация**:
- **`README.md`** - Детальная техническая спецификация системы
- **`monitoring/README.md`** - Руководство по мониторингу и метрикам
- **`CLAUDE.md`** (этот файл) - Инструкции для AI-ассистента

## Общие правила работы

- **Честность**: Если не знаешь ответ - так и скажи. Не придумывай информацию.
- **Остановка при зацикливании**: Если выполнение задач зациклилось - остановись, спроси что делать дальше.
- **Комментарии**: Пиши подробные комментарии в коде на русском языке.
- **Язык общения**: Отвечай на русском языке.
- **Документация**: При вопросах по архитектуре/технологиям - читай `README-PROJECT.md` и `DEVELOPMENT-GUIDE.md` в первую очередь.

## 🔴 КРИТИЧЕСКИ ВАЖНО: Docker Compose

**ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ №1**: Для запуска, тестирования и работы с проектом использовать ТОЛЬКО файлы `docker-compose*.yml` из **КОРНЯ ПРОЕКТА** (`/home/artur/Projects/artStore/`).

**ВСЕГДА**:
- ✅ `cd /home/artur/Projects/artStore` перед любыми docker-compose командами
- ✅ Использовать корневой `docker-compose.yml` для всех операций
- ✅ Запускать `docker-compose build [module-name]` из корня
- ✅ Запускать `docker-compose up -d [module-name]` из корня

**НИКОГДА**:
- ❌ НЕ использовать docker-compose из поддиректорий (admin-module/, ingester-module/, etc.)
- ❌ НЕ создавать собственные docker-compose файлы
- ❌ НЕ запускать модули напрямую без Docker

## Инфраструктура

**Базовые компоненты** (запускаются через `docker-compose.yml`):
- **PostgreSQL** (port 5432) - основная БД
- **Redis** (port 6379) - Service Discovery и кеширование
- **MinIO** (ports 9000/9001) - S3-совместимое хранилище
- **PgAdmin** (port 5050) - веб-интерфейс для PostgreSQL

**Credentials**: См. `docker-compose.yml` для логинов/паролей всех сервисов.

**Database operations**: Используй инструменты внутри контейнера postgres. Создавай базы данных по необходимости.

**Authentication**: Только OAuth 2.0 Client Credentials (LDAP и Dex OIDC удалены в Sprint 13).

## Ключевые архитектурные принципы

**Для детального понимания архитектуры см. `README-PROJECT.md`**

### Критически важные концепции

1. **Attribute-First Storage Model**: Файлы `*.attr.json` - единственный источник истины для метаданных
2. **JWT RS256 Authentication**: Центральная аутентификация через Admin Module с публичным ключом
3. **Redis SYNC Mode**: Все модули используют синхронный redis-py (не asyncio) для Service Discovery
4. **PostgreSQL ASYNC**: Database операции через asyncpg
5. **WAL Protocol**: Write-Ahead Log для атомарности операций с файлами
6. **Saga Pattern**: Координация распределенных транзакций через Admin Module
7. **Circuit Breaker**: Graceful degradation при недоступности dependencies

### Service Discovery Pattern

- Admin Module публикует конфигурацию storage-elements в Redis
- Ingester/Query подписываются на обновления через Redis Pub/Sub
- Fallback на локальную конфигурацию при недоступности Redis

## Быстрый старт

**Подробнее см. `DEVELOPMENT-GUIDE.md`**

### Запуск окружения

```bash
cd /home/artur/Projects/artStore

# Запуск инфраструктуры + все модули
docker-compose up -d

# Мониторинг (опционально)
docker-compose -f docker-compose.monitoring.yml up -d
```

### Python Virtual Environment

**ЕДИНЫЙ .venv для всех Python модулей**: `/home/artur/Projects/artStore/.venv`

```bash
# Создание (один раз)
python3 -m venv .venv

# Активация
source .venv/bin/activate

# Установка зависимостей всех модулей
pip install -r admin-module/requirements.txt
pip install -r storage-element/requirements.txt
pip install -r ingester-module/requirements.txt
pip install -r query-module/requirements.txt
```

### Service Ports

- PostgreSQL: 5432, PgAdmin: 5050, Redis: 6379, MinIO: 9000/9001
- Admin Module: 8000-8009, Storage: 8010-8019, Ingester: 8020-8029, Query: 8030-8039, UI: 4200

## Архитектура модулей

**Подробное описание каждого модуля см. в их README-PROJECT.md**

### Модули системы

1. **Admin Module** (порты 8000-8009) - Аутентификация и управление
   - OAuth 2.0 JWT (RS256), Service Accounts, Saga координация
   - См. `admin-module/README-PROJECT.md`

2. **Storage Element** (порты 8010-8019) - Физическое хранение файлов
   - Режимы: edit, rw, ro, ar
   - WAL protocol, attr.json файлы
   - См. `storage-element/README-PROJECT.md`

3. **Ingester Module** (порты 8020-8029) - Загрузка файлов
   - Streaming upload, validation, compression
   - См. `ingester-module/README-PROJECT.md`

4. **Query Module** (порты 8030-8039) - Поиск и скачивание
   - PostgreSQL Full-Text Search, multi-level caching
   - См. `query-module/README-PROJECT.md`

5. **Admin UI** (порт 4200) - Angular веб-интерфейс
   - Dashboard, управление аккаунтами, file manager
   - См. `admin-ui/README-PROJECT.md`

## Основные команды

**Полное руководство см. `DEVELOPMENT-GUIDE.md`**

### Запуск и управление

```bash
cd /home/artur/Projects/artStore

# Запуск всей системы
docker-compose up -d

# Просмотр логов
docker-compose logs -f [module-name]

# Пересборка модуля
docker-compose build [module-name]
docker-compose up -d [module-name]

# Остановка
docker-compose down
```

### Тестирование

```bash
# Активировать venv
source .venv/bin/activate

# Запуск тестов модуля
cd [module-name]
pytest tests/ -v

# С coverage
pytest tests/ --cov=app --cov-report=html
```

### Database

```bash
# Подключение к PostgreSQL
docker exec -it artstore_postgres psql -U artstore -d artstore

# Создание новой БД
docker exec -it artstore_postgres createdb -U artstore [db_name]
```

## Важные концепции

### Storage Element Modes

- **edit**: Full CRUD (не меняется через API)
- **rw**: Read-write без deletion (переход в ro через API)
- **ro**: Read-only (переход в ar через API)
- **ar**: Archive mode (только через конфиг + restart)

### Логирование

**Production**: JSON формат ОБЯЗАТЕЛЕН (`LOG_FORMAT=json`)
**Development**: Text формат разрешен (`LOG_FORMAT=text`)

### Configuration Priority

Environment variables > config files

Примеры конфигураций см. в модульных README-PROJECT.md

## Credentials

### Initial Service Account

Автоматически создается при первом запуске:
- Name: `admin-service`
- Role: `ADMIN`
- Client ID/Secret: Автогенерация
- **ВАЖНО**: `is_system=True` - не удаляется через API
- **PRODUCTION**: Обязательно изменить client_secret через `.env`

### OAuth 2.0 пример

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "...", "client_secret": "..."}'
```

### Infrastructure Credentials

См. `docker-compose.yml`:
- PostgreSQL: artstore / password
- PgAdmin: admin@admin.com / password
- MinIO: minioadmin / minioadmin

## Критические требования реализации

**Полный список см. `README-PROJECT.md` → "Критические требования"**

### Важнейшие правила

1. **Consistency Protocol**: WAL → Attr File → DB Cache → Service Discovery → Commit (строго в порядке)
2. **Attribute Files First**: Всегда сначала запись в `*.attr.json`, затем в DB cache
3. **Stateless Design**: Все модули должны быть stateless
4. **Circuit Breaker**: Обязателен для всех inter-service communications
5. **Redis SYNC Mode**: Используй синхронный redis-py для Service Discovery
6. **PostgreSQL ASYNC**: Используй asyncpg для database операций

## Мониторинг

**Полная документация см. `monitoring/README.md`**

### Быстрый старт

```bash
# Запуск мониторинга
docker-compose -f docker-compose.monitoring.yml up -d

# Доступ к интерфейсам
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin / admin123)
# AlertManager: http://localhost:9093
```

### Компоненты

- **OpenTelemetry**: Distributed tracing во всех модулях
- **Prometheus**: Метрики на `/metrics` каждого модуля
- **Grafana**: Pre-configured dashboards
- **AlertManager**: Critical/Warning alerts
- **Health Checks**: `/health/live` и `/health/ready` на всех модулях

## Безопасность

**Полные требования см. `README-PROJECT.md` → "Security Framework"**

### Ключевые принципы

1. **TLS 1.3**: Все межсервисные соединения
2. **JWT RS256**: Access tokens (30 min), автоматическая ротация ключей (24ч)
3. **Bearer Authentication**: Обязательна для всех API (кроме /health)
4. **Audit Logging**: Все операции с tamper-proof signatures
5. **Rate Limiting**: Adaptive limiting с автоблокировкой
6. **RBAC**: Fine-grained resource-level permissions

### Production Checklist

- [ ] Изменить все default credentials в `.env`
- [ ] Настроить TLS сертификаты
- [ ] Включить audit logging
- [ ] Настроить rate limiting
- [ ] Проверить CORS политики
- [ ] Включить automated vulnerability scanning