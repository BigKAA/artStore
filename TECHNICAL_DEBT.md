# Технологический долг ArtStore

Этот файл отслеживает известные технические долги, требующие устранения в будущем.

## Формат записи

```markdown
### [ПРИОРИТЕТ] Название задачи
**Модуль**: название модуля
**Дата добавления**: YYYY-MM-DD
**Оценка сложности**: низкая/средняя/высокая
**Описание**: Подробное описание проблемы
**План устранения**: Шаги для решения
**Связанные файлы**: Список затронутых файлов
```

---

## 🔴 Критический долг

### [CRITICAL] Миграция логирования на JSON формат

**Модуль**: Все модули
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя
**Описание**:
- Все production логи ДОЛЖНЫ быть в JSON формате для интеграции с ELK Stack, Splunk и другими системами анализа
- Текущее состояние: некоторые модули используют text формат
- JSON формат обязателен для production, text разрешен только в development режиме

**План устранения**:
1. Проверить все модули на использование JSON логирования
2. Обновить конфигурацию logging во всех модулях:
   - `LOG_FORMAT=json` для production (docker-compose.yml)
   - `LOG_FORMAT=text` только для development (docker-compose.dev.yml)
3. Обеспечить обязательные поля в логах:
   - timestamp, level, logger, message, module, function, line
   - request_id, user_id, trace_id (для OpenTelemetry интеграции)
4. Использовать python-json-logger или аналоги для structured logging
5. Добавить валидацию формата логов в CI/CD pipeline

**Связанные файлы**:
- `admin-module/app/core/logging_config.py`
- `storage-element/app/core/logging_config.py`
- `ingester-module/app/core/logging_config.py`
- `query-module/app/core/logging_config.py`
- Все `docker-compose.yml` файлы
- `CLAUDE.md` (требования к логированию)

**Ссылки**:
- [CLAUDE.md:53-63](file:///home/artur/Projects/artStore/CLAUDE.md#L53-L63) - Требования к логированию

---

### [CRITICAL] Создание LDIF структуры LDAP хранилища

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя
**Описание**:
- Отсутствует LDIF файл с базовой структурой LDAP хранилища для ArtStore
- Необходим для инициализации LDAP сервера с правильной структурой OU, групп и маппинга на роли
- Требуется для корректной работы LDAP аутентификации в Admin Module

**План устранения**:
1. Создать базовый LDIF файл с структурой:
   ```
   dc=artstore,dc=local
   ├── ou=users
   ├── ou=groups
   │   ├── cn=admins (role=admin)
   │   ├── cn=operators (role=operator)
   │   └── cn=users (role=user)
   └── ou=service-accounts
   ```
2. Добавить примеры пользователей для каждой роли
3. Настроить docker-compose.yml для автоматической загрузки LDIF при старте
4. Документировать структуру в README
5. Добавить инструкции по ручной настройке LDAP

**Связанные файлы**:
- Создать: `admin-module/ldap/base-structure.ldif`
- Создать: `admin-module/ldap/test-users.ldif`
- Обновить: `docker-compose.yml` (volume mount для LDIF)
- Обновить: `admin-module/README.md` (документация LDAP)
- Связано с: `admin-module/app/services/ldap_service.py`

**Требования к структуре**:
```ldif
# Base structure
dn: dc=artstore,dc=local
objectClass: top
objectClass: dcObject
objectClass: organization
o: ArtStore
dc: artstore

# Users organizational unit
dn: ou=users,dc=artstore,dc=local
objectClass: organizationalUnit
ou: users

# Groups organizational unit
dn: ou=groups,dc=artstore,dc=local
objectClass: organizationalUnit
ou: groups

# Admin group (maps to UserRole.ADMIN)
dn: cn=admins,ou=groups,dc=artstore,dc=local
objectClass: groupOfUniqueNames
cn: admins
uniqueMember: uid=admin,ou=users,dc=artstore,dc=local

# Operator group (maps to UserRole.OPERATOR)
dn: cn=operators,ou=groups,dc=artstore,dc=local
objectClass: groupOfUniqueNames
cn: operators
uniqueMember: uid=operator,ou=users,dc=artstore,dc=local

# User group (maps to UserRole.USER)
dn: cn=users,ou=groups,dc=artstore,dc=local
objectClass: groupOfUniqueNames
cn: users
uniqueMember: uid=user,ou=users,dc=artstore,dc=local

# Test users
dn: uid=admin,ou=users,dc=artstore,dc=local
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: top
uid: admin
cn: Admin User
sn: User
givenName: Admin
mail: admin@artstore.local
userPassword: {SSHA}... # bcrypt hash

dn: uid=operator,ou=users,dc=artstore,dc=local
objectClass: inetOrgPerson
uid: operator
cn: Operator User
sn: User
givenName: Operator
mail: operator@artstore.local
userPassword: {SSHA}...

dn: uid=user,ou=users,dc=artstore,dc=local
objectClass: inetOrgPerson
uid: user
cn: Regular User
sn: User
givenName: Regular
mail: user@artstore.local
userPassword: {SSHA}...
```

**Ссылки**:
- [CLAUDE.md:321](file:///home/artur/Projects/artStore/CLAUDE.md#L321) - LDAP интеграция
- [docker-compose.yml](file:///home/artur/Projects/artStore/docker-compose.yml) - LDAP сервис

---

## 🟡 Важный долг

### [HIGH] API Endpoint Integration Tests

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя
**Описание**:
- API endpoint тесты в `test_auth_integration.py` требуют dependency injection для test database
- Текущее состояние: 3 из 9 API tests падают из-за использования production database
- AuthService integration tests все проходят (13/13)

**План устранения**:
1. Создать dependency override для database session в API tests
2. Использовать `app.dependency_overrides` для подмены get_db
3. Настроить AsyncClient для работы с test event loop
4. Исправить проблему "Event loop is closed" при teardown
5. Добавить фикстуру для автоматической подмены dependencies

**Связанные файлы**:
- `admin-module/tests/integration/test_auth_integration.py` (TestAuthAPIEndpoints)
- `admin-module/tests/conftest.py` (client fixture)
- `admin-module/app/api/dependencies.py`

**Статус**: 6/9 API endpoint tests проходят, 3 требуют доработки

---

### [HIGH] Password Reset Implementation

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя
**Описание**:
- Методы `create_password_reset_token` и `reset_password` возвращают заглушки
- Нужна реализация через Redis с TTL для токенов
- Требуется email отправка с токеном сброса

**План устранения**:
1. Создать Redis-based token storage с TTL (15 минут)
2. Интегрировать email service (SMTP)
3. Создать endpoint для инициации сброса пароля
4. Создать endpoint для валидации токена и установки нового пароля
5. Добавить rate limiting для prevent abuse
6. Написать integration tests

**Связанные файлы**:
- `admin-module/app/services/auth_service.py:258-314`
- Создать: `admin-module/app/services/email_service.py`
- Обновить: `admin-module/app/api/v1/endpoints/auth.py`

---

### [MEDIUM] pytest-asyncio Dependency

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: низкая
**Описание**:
- `pytest-asyncio` установлен в runtime, но отсутствует в requirements.txt
- Может вызвать проблемы при CI/CD или на других машинах

**План устранения**:
1. Добавить `pytest-asyncio>=1.3.0` в `requirements.txt` или `requirements-dev.txt`
2. Документировать в README.md необходимость установки dev dependencies
3. Обновить CI/CD pipeline для установки test dependencies

**Связанные файлы**:
- `admin-module/requirements.txt` или создать `requirements-dev.txt`
- `admin-module/README.md`
- `.github/workflows/tests.yml` (если есть CI)

---

## 🟢 Низкий приоритет

### [LOW] Test Coverage для API Endpoints

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: средняя
**Описание**:
- API endpoint tests покрывают только базовый happy path и простые error cases
- Отсутствуют тесты для edge cases (expired tokens, concurrent requests, rate limiting)
- Нет performance tests для authentication endpoints

**План устранения**:
1. Добавить edge case tests:
   - Concurrent login attempts
   - Token refresh race conditions
   - Session hijacking scenarios
2. Добавить security tests:
   - SQL injection attempts
   - JWT tampering
   - Brute force protection
3. Добавить performance tests:
   - Load testing для /login endpoint
   - Stress testing для token validation

**Связанные файлы**:
- `admin-module/tests/integration/test_auth_integration.py`
- Создать: `admin-module/tests/security/`
- Создать: `admin-module/tests/performance/`

---

### [LOW] Docker Healthcheck Enhancement

**Модуль**: admin-module
**Дата добавления**: 2025-01-10
**Оценка сложности**: низкая
**Описание**:
- Healthcheck только проверяет `/health/live` endpoint
- Не проверяет готовность dependencies (PostgreSQL, Redis)
- Start period увеличен до 40s как временное решение

**План устранения**:
1. Добавить `/health/ready` endpoint с проверкой dependencies
2. Использовать `/health/ready` в HEALTHCHECK
3. Уменьшить start-period обратно до разумных значений
4. Добавить dependency checks в health endpoint

**Связанные файлы**:
- `admin-module/Dockerfile:59-61`
- `admin-module/app/api/v1/endpoints/health.py`

---

## Процесс работы с техническим долгом

### Добавление нового долга
1. Добавить запись в соответствующий раздел по приоритету
2. Заполнить все обязательные поля
3. Указать оценку сложности и связанные файлы
4. Сделать commit: `docs: add technical debt - [название]`

### Устранение долга
1. Создать feature branch: `debt/название-долга`
2. Реализовать решение согласно плану устранения
3. Обновить статус в этом файле или удалить запись
4. Сделать commit: `fix: resolve technical debt - [название]`

### Приоритезация
- 🔴 **CRITICAL**: Блокирует production deployment или создает security риски
- 🟡 **HIGH**: Важно для качества, но не блокирует работу
- 🟢 **MEDIUM**: Улучшения качества кода
- ⚪ **LOW**: Nice to have, можно отложить

### Ревью долга
- Еженедельный ревью новых долгов на team meeting
- Ежемесячный ревью приоритетов существующих долгов
- Квартальная цель: устранение минимум 50% CRITICAL и HIGH долгов

---

**Последнее обновление**: 2025-01-10
**Общее количество долгов**: 7 (2 CRITICAL, 3 HIGH, 2 LOW)
