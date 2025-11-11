# Session 2025-01-11: LDAP Structure Complete

**Дата**: 2025-01-11
**Задача**: Создать LDIF файлы и загрузить в LDAP сервер
**Статус**: ✅ Завершено успешно

## Выполненные работы

### 1. Создана структура LDAP директории

**Директория**: `/home/artur/Projects/artStore/.ldap/`

**Файлы**:
- `base-structure.ldif` - Полная базовая структура (reference)
- `base-structure-final.ldif` - Загруженная структура (без дублирующих OU)
- `test-users.ldif` - Тестовые пользователи
- `README.md` - Подробная документация

### 2. Загружена базовая структура в LDAP

**Созданные OU (Organizational Units)**:
- `ou=users,dc=artstore,dc=local` - Активные пользователи (search base)
- `ou=dismissed,dc=artstore,dc=local` - Деактивированные пользователи
- `ou=Groups,dc=artstore,dc=local` - Группы (уже существовал)

**Service Account**:
- DN: `cn=readonly,dc=artstore,dc=local`
- Password: `readonly_secret_password`
- Назначение: Read-only доступ для синхронизации Admin Module

**Группы** (используют `groupOfUniqueNames` и `uniqueMember`):
- `cn=artstore-admins,ou=Groups,dc=artstore,dc=local` - Маппинг на ADMIN role
- `cn=artstore-operators,ou=Groups,dc=artstore,dc=local` - Маппинг на OPERATOR role
- `cn=artstore-users,ou=Groups,dc=artstore,dc=local` - Маппинг на USER role

### 3. Загружены тестовые пользователи

| Username | Password | Email | Role | Group | DN |
|----------|----------|-------|------|-------|-----|
| ivanov | test123 | ivanov@artstore.local | ADMIN | artstore-admins | uid=ivanov,ou=users,dc=artstore,dc=local |
| petrov | test123 | petrov@artstore.local | OPERATOR | artstore-operators | uid=petrov,ou=users,dc=artstore,dc=local |
| sidorov | test123 | sidorov@artstore.local | USER | artstore-users | uid=sidorov,ou=users,dc=artstore,dc=local |

### 4. Протестирована структура

**Тесты выполнены**:
1. ✅ Поиск всех пользователей в `ou=users` - найдено 3 пользователя
2. ✅ Поиск всех групп - найдено 5 групп (3 новых + 2 старых)
3. ✅ Проверка членства в группах - все пользователи корректно добавлены
4. ✅ Аутентификация пользователя ivanov - успешно

**Команды для тестирования**:
```bash
# Поиск пользователей
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password \
  -b "ou=users,dc=artstore,dc=local" \
  "(objectClass=inetOrgPerson)" uid cn mail

# Поиск групп
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password \
  -b "ou=Groups,dc=artstore,dc=local" \
  "(objectClass=groupOfUniqueNames)" cn uniqueMember

# Тест аутентификации
docker exec artstore_ldap ldapwhoami -x -H ldap://localhost:3389 \
  -D "uid=ivanov,ou=users,dc=artstore,dc=local" -w test123
```

## Архитектурные решения

### groupOfUniqueNames вместо groupOfNames

**Причина**: 389 Directory Server лучше работает с `groupOfUniqueNames`
- Использует атрибут `uniqueMember` (уникальные члены)
- `groupOfNames` использует `member` (может быть дубликаты)
- Более строгая семантика для enterprise использования

### ou=Groups с заглавной буквы

**Причина**: Консистентность с существующей структурой
- 389 DS автоматически создал `ou=Groups` при инициализации
- LDAP DN case-insensitive, но сохраняет регистр
- Используем существующий OU вместо создания дубликата

### Структура директории

```
dc=artstore,dc=local
├── ou=users (search base для активных пользователей)
│   ├── uid=ivanov (ADMIN)
│   ├── uid=petrov (OPERATOR)
│   └── uid=sidorov (USER)
├── ou=dismissed (деактивированные, за пределами search base)
├── ou=Groups (группы для role mapping)
│   ├── cn=artstore-admins → ADMIN role
│   ├── cn=artstore-operators → OPERATOR role
│   └── cn=artstore-users → USER role
└── cn=readonly (service account для синхронизации)
```

**Rationale**:
- `ou=users` - search base для Admin Module (активные пользователи)
- `ou=dismissed` - деактивированные пользователи (не попадают в search)
- `ou=Groups` - группы для role mapping (LDAP groups → ArtStore roles)
- `cn=readonly` - read-only service account (минимальные привилегии)

## Подключение из Admin Module

### Connection Settings для config.yaml

```yaml
ldap:
  enabled: true
  server: "ldap://localhost:1389"  # Host port mapping (внутри контейнера 3389)
  use_tls: false  # true для production

  # Read-only bind для синхронизации
  bind_dn: "cn=readonly,dc=artstore,dc=local"
  bind_password: "readonly_secret_password"

  # Search settings
  users:
    base_dn: "ou=users,dc=artstore,dc=local"
    filter: "(objectClass=inetOrgPerson)"
    attributes:
      - uid
      - mail
      - cn
      - sn
      - givenName

  groups:
    base_dn: "ou=Groups,dc=artstore,dc=local"
    filter: "(objectClass=groupOfUniqueNames)"
    member_attribute: "uniqueMember"

  # Group → Role mapping
  role_mappings:
    "cn=artstore-admins,ou=Groups,dc=artstore,dc=local": "ADMIN"
    "cn=artstore-operators,ou=Groups,dc=artstore,dc=local": "OPERATOR"
    "cn=artstore-users,ou=Groups,dc=artstore,dc=local": "USER"
```

### User Authentication Flow

```python
# 1. User login с LDAP credentials
user_dn = "uid=ivanov,ou=users,dc=artstore,dc=local"
password = "test123"

# 2. LIVE LDAP bind (аутентификация)
conn = ldap.initialize("ldap://localhost:1389")
conn.simple_bind_s(user_dn, password)  # Проверка пароля

# 3. Получить user attributes
result = conn.search_s(user_dn, ldap.SCOPE_BASE, 
    "(objectClass=*)", ['uid', 'mail', 'cn', 'sn', 'givenName'])

# 4. Получить group membership
groups = conn.search_s("ou=Groups,dc=artstore,dc=local", 
    ldap.SCOPE_SUBTREE, f"(uniqueMember={user_dn})", ['cn'])

# 5. Map LDAP group → ArtStore role
# cn=artstore-admins → Role.ADMIN

# 6. Create/Update user в PostgreSQL cache

# 7. Generate JWT tokens (access + refresh)
```

## Технический долг - обновлен

### ✅ RESOLVED: LDAP Structure
- **Было**: Нет LDAP структуры и тестовых пользователей
- **Стало**: Полная структура создана и протестирована
- **Файлы**: .ldap/base-structure-final.ldif, test-users.ldif, README.md

### ⏳ NEXT: LDAP Integration Implementation

**Phase 1: Database Models** (приоритет HIGH):
1. Создать Alembic migration для LDAP полей
   - `User.source` (LOCAL/LDAP)
   - `User.ldap_dn` (Distinguished Name)
   - `User.last_sync_at` (timestamp)
   - Constraint: password_hash NULL для LDAP users

2. Обновить User model в admin-module/app/models/user.py

**Phase 2: Core Services** (приоритет HIGH):
3. Реализовать LDAPConnectionPool (connection management)
4. Реализовать LDAPAuthService (authentication через LDAP bind)
5. Реализовать LDAPSyncService (periodic sync background task)
6. Реализовать GroupMappingService (LDAP groups → ArtStore roles)

**Phase 3: API Integration** (приоритет MEDIUM):
7. Модифицировать AuthService для диспетчеризации LOCAL vs LDAP
8. Добавить POST /api/users/me/password (self-service password change)
9. Модифицировать GET /api/users (добавить source filter)
10. Добавить POST /api/ldap/sync (manual trigger для admins)

**Phase 4: Configuration** (приоритет MEDIUM):
11. Добавить LDAP секцию в config.yaml
12. Добавить environment variables (.env)
13. Создать config validation

**Phase 5: Testing** (приоритет MEDIUM):
14. Unit tests для LDAPAuthService
15. Unit tests для LDAPSyncService
16. Integration tests с реальным LDAP
17. E2E tests для login flow

## Следующие действия

### Immediate Next (сегодня/завтра):
1. **Создать Alembic migration** для LDAP support
2. **Обновить User model** с LDAP полями
3. **Добавить LDAP конфигурацию** в config.yaml

### Short-term (эта неделя):
4. **Реализовать LDAPAuthService**
5. **Реализовать LDAPSyncService**
6. **Интегрировать в AuthService**

### Medium-term (следующая неделя):
7. **API endpoints** для LDAP management
8. **Тестирование** (unit + integration)
9. **Документация** (API docs, setup guide)

## Lessons Learned

1. **389 Directory Server особенности**:
   - Внутренний порт 3389 (не стандартный 389)
   - Автоматически создает ou=Groups при инициализации
   - Лучше работает с groupOfUniqueNames, чем groupOfNames

2. **LDAP DN case sensitivity**:
   - DN case-insensitive для поиска
   - Но сохраняет регистр при создании
   - Важно использовать консистентный регистр

3. **LDIF файлы**:
   - Проще создавать финальный файл без дублирующих записей
   - Использовать changetype: modify для добавления в группы
   - Тестировать структуру перед массовой загрузкой

## Метрики сессии

- **Время выполнения**: ~30 минут
- **Созданные файлы**: 4 (.ldif + README.md)
- **Загружено записей**: 7 (3 users + 3 groups + 1 service account)
- **Выполнено тестов**: 4 (search, groups, auth, whoami)
- **Обнаружено проблем**: 2 (groupOfNames → groupOfUniqueNames, ou=groups → ou=Groups)
- **Проблемы решены**: 2 (обе решены успешно)

## Статус проекта после сессии

### Admin Module: 95% → 96%
- ✅ LDAP Structure созда и протестирована (+1%)
- ⏳ LDAP Integration services (pending)
- ⏳ LDAP Configuration (pending)
- ⏳ Database migration (pending)

### Overall Progress: 44% → 45%
- Infrastructure: 30% → 35% (+5% за LDAP setup)
- Admin Module: 95% → 96%
- Остальные модули без изменений

## Commands Reference

### Полезные команды для работы с LDAP

```bash
# Загрузка структуры
cd /home/artur/Projects/artStore/.ldap
docker exec -i artstore_ldap ldapadd -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password < base-structure-final.ldif

# Поиск всех пользователей
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password \
  -b "ou=users,dc=artstore,dc=local" "(objectClass=inetOrgPerson)"

# Проверка групп
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password \
  -b "ou=Groups,dc=artstore,dc=local" "(objectClass=groupOfUniqueNames)"

# Тест аутентификации
docker exec artstore_ldap ldapwhoami -x -H ldap://localhost:3389 \
  -D "uid=ivanov,ou=users,dc=artstore,dc=local" -w test123

# Удаление всей структуры (для сброса)
docker exec artstore_ldap ldapdelete -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password -r "dc=artstore,dc=local"
```
