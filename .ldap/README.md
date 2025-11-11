# ArtStore LDAP Configuration

Конфигурация LDAP для интеграции с Admin Module.

## Структура директории

```
dc=artstore,dc=local
├── ou=users (активные пользователи, search base)
│   ├── uid=ivanov (ADMIN)
│   ├── uid=petrov (OPERATOR)
│   └── uid=sidorov (USER)
├── ou=dismissed (деактивированные пользователи)
├── ou=Groups (группы)
│   ├── cn=artstore-admins (маппинг → ADMIN role)
│   ├── cn=artstore-operators (маппинг → OPERATOR role)
│   └── cn=artstore-users (маппинг → USER role)
└── cn=readonly (service account для синхронизации)
```

## Файлы

- **base-structure.ldif** - Полная структура (для reference)
- **base-structure-final.ldif** - Загруженная структура (без дублирующих OU)
- **test-users.ldif** - Тестовые пользователи

## Загрузка в LDAP

### Первичная загрузка (уже выполнена)

```bash
# Базовая структура
docker exec -i artstore_ldap ldapadd -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password < base-structure-final.ldif

# Тестовые пользователи
docker exec -i artstore_ldap ldapadd -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password < test-users.ldif
```

### Повторная загрузка (если нужно сбросить)

```bash
# Удалить все данные под dc=artstore,dc=local
docker exec artstore_ldap ldapdelete -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password -r "dc=artstore,dc=local"

# Пересоздать base DN
docker exec artstore_ldap ldapadd -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password <<EOF
dn: dc=artstore,dc=local
objectClass: top
objectClass: domain
dc: artstore
EOF

# Загрузить структуру заново
docker exec -i artstore_ldap ldapadd -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password < base-structure-final.ldif
docker exec -i artstore_ldap ldapadd -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password < test-users.ldif
```

## Тестовые пользователи

| Username | Password | Email | Role | Group |
|----------|----------|-------|------|-------|
| ivanov | test123 | ivanov@artstore.local | ADMIN | artstore-admins |
| petrov | test123 | petrov@artstore.local | OPERATOR | artstore-operators |
| sidorov | test123 | sidorov@artstore.local | USER | artstore-users |

## Service Account

**Readonly Account для синхронизации:**
- DN: `cn=readonly,dc=artstore,dc=local`
- Password: `readonly_secret_password`
- Permissions: READ only на ou=users, ou=Groups

## Проверка структуры

### Поиск всех пользователей
```bash
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password \
  -b "ou=users,dc=artstore,dc=local" \
  "(objectClass=inetOrgPerson)" uid cn mail
```

### Поиск всех групп
```bash
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password \
  -b "ou=Groups,dc=artstore,dc=local" \
  "(objectClass=groupOfUniqueNames)" cn uniqueMember
```

### Проверка аутентификации пользователя
```bash
docker exec artstore_ldap ldapwhoami -x -H ldap://localhost:3389 \
  -D "uid=ivanov,ou=users,dc=artstore,dc=local" -w test123
```

Результат должен быть:
```
dn: uid=ivanov,ou=users,dc=artstore,dc=local
```

### Проверка членства в группах
```bash
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "uid=ivanov,ou=users,dc=artstore,dc=local" -w test123 \
  -b "uid=ivanov,ou=users,dc=artstore,dc=local" \
  "(objectClass=*)" dn
```

Затем найти группу:
```bash
docker exec artstore_ldap ldapsearch -x -H ldap://localhost:3389 \
  -D "cn=readonly,dc=artstore,dc=local" -w readonly_secret_password \
  -b "ou=Groups,dc=artstore,dc=local" \
  "(uniqueMember=uid=ivanov,ou=users,dc=artstore,dc=local)" cn
```

## Подключение из Admin Module

### Connection Settings
```yaml
ldap:
  enabled: true
  server: "ldap://localhost:1389"  # Host port mapping

  # Read-only bind
  bind_dn: "cn=readonly,dc=artstore,dc=local"
  bind_password: "readonly_secret_password"

  # Search settings
  users:
    base_dn: "ou=users,dc=artstore,dc=local"
    filter: "(objectClass=inetOrgPerson)"

  groups:
    base_dn: "ou=Groups,dc=artstore,dc=local"
    filter: "(objectClass=groupOfUniqueNames)"
    member_attribute: "uniqueMember"

  # Role mapping
  role_mappings:
    "cn=artstore-admins,ou=Groups,dc=artstore,dc=local": "ADMIN"
    "cn=artstore-operators,ou=Groups,dc=artstore,dc=local": "OPERATOR"
    "cn=artstore-users,ou=Groups,dc=artstore,dc=local": "USER"
```

### Test Authentication from Python
```python
import ldap

# Connect
conn = ldap.initialize("ldap://localhost:1389")

# User bind (authentication)
user_dn = "uid=ivanov,ou=users,dc=artstore,dc=local"
password = "test123"

try:
    conn.simple_bind_s(user_dn, password)
    print("Authentication successful!")

    # Search user attributes
    result = conn.search_s(
        user_dn,
        ldap.SCOPE_BASE,
        "(objectClass=*)",
        ['uid', 'mail', 'cn', 'sn', 'givenName']
    )
    print(f"User attributes: {result}")

    # Search group membership
    groups = conn.search_s(
        "ou=Groups,dc=artstore,dc=local",
        ldap.SCOPE_SUBTREE,
        f"(uniqueMember={user_dn})",
        ['cn']
    )
    print(f"User groups: {[g[1]['cn'][0].decode() for g in groups]}")

except ldap.INVALID_CREDENTIALS:
    print("Invalid credentials!")
finally:
    conn.unbind_s()
```

## Операции управления

### Добавить нового пользователя
```bash
docker exec -i artstore_ldap ldapadd -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password <<EOF
dn: uid=newuser,ou=users,dc=artstore,dc=local
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: newuser
cn: New User
sn: User
givenName: New
mail: newuser@artstore.local
userPassword: password123
EOF
```

### Добавить пользователя в группу
```bash
docker exec -i artstore_ldap ldapmodify -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password <<EOF
dn: cn=artstore-users,ou=Groups,dc=artstore,dc=local
changetype: modify
add: uniqueMember
uniqueMember: uid=newuser,ou=users,dc=artstore,dc=local
EOF
```

### Деактивировать пользователя (перемещение в ou=dismissed)
```bash
docker exec -i artstore_ldap ldapmodrdn -x -H ldap://localhost:3389 \
  -D "cn=Directory Manager" -w password \
  "uid=sidorov,ou=users,dc=artstore,dc=local" \
  "uid=sidorov" \
  -n "ou=dismissed,dc=artstore,dc=local"
```

### Изменить пароль пользователя (self-service)
```bash
docker exec -i artstore_ldap ldappasswd -x -H ldap://localhost:3389 \
  -D "uid=ivanov,ou=users,dc=artstore,dc=local" \
  -w test123 \
  -s new_password123 \
  "uid=ivanov,ou=users,dc=artstore,dc=local"
```

## Архитектурные решения

### Почему groupOfUniqueNames вместо groupOfNames?
- **groupOfUniqueNames** использует `uniqueMember` (уникальные члены)
- **groupOfNames** использует `member` (может быть дубликаты)
- 389 Directory Server лучше работает с groupOfUniqueNames

### Почему ou=Groups с заглавной буквы?
- LDAP case-insensitive для DN, но сохраняет регистр
- 389 DS по умолчанию создает ou=Groups (заглавная G)
- Используем существующий OU для консистентности

### Структура директории
- **ou=users** - активные пользователи (search base для Admin Module)
- **ou=dismissed** - деактивированные (за пределами search base)
- **ou=Groups** - группы для role mapping
- **cn=readonly** - service account с READ-only правами

## Troubleshooting

### LDAP сервер не отвечает
```bash
# Проверить статус контейнера
docker ps | grep ldap

# Проверить логи
docker logs artstore_ldap

# Перезапустить контейнер
docker restart artstore_ldap
```

### Ошибка "Can't contact LDAP server"
- Проверить порт: внутри контейнера 3389, снаружи 1389
- Использовать `-H ldap://localhost:3389` внутри контейнера
- Использовать `ldap://localhost:1389` с хоста

### Ошибка "Already exists"
- Запись уже существует в LDAP
- Использовать `ldapsearch` для проверки
- Использовать `ldapmodify` вместо `ldapadd` для обновления

### Проверка прав readonly аккаунта
```bash
# Попытка изменить данные (должна упасть с insufficient access)
docker exec -i artstore_ldap ldapmodify -x -H ldap://localhost:3389 \
  -D "cn=readonly,dc=artstore,dc=local" -w readonly_secret_password <<EOF
dn: uid=ivanov,ou=users,dc=artstore,dc=local
changetype: modify
replace: mail
mail: test@test.com
EOF
```

Результат должен быть: `Insufficient access (50)`

## Следующие шаги

1. ✅ LDAP структура создана и протестирована
2. ⏳ Реализовать LDAPAuthService в Admin Module
3. ⏳ Реализовать LDAPSyncService для периодической синхронизации
4. ⏳ Добавить LDAP конфигурацию в config.yaml
5. ⏳ Создать Alembic migration для поддержки LDAP users
6. ⏳ Написать интеграционные тесты с реальным LDAP

## Reference

- [389 Directory Server Documentation](https://directory.fedoraproject.org/docs/389ds/documentation.html)
- [LDAP RFC 4511](https://tools.ietf.org/html/rfc4511)
- [python-ldap Documentation](https://www.python-ldap.org/)
