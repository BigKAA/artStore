# LDAP Integration Specification для ArtStore Admin Module

**Дата создания**: 2025-01-11
**Статус**: Финальная спецификация, готова к реализации

## Архитектурное решение

### Главный принцип: Admin Module НЕ управляет LDAP (CRUD)

**Rationale:**
- Security: принцип наименьших привилегий
- Enterprise compliance: LDAP управляется централизованно IT Infrastructure
- Separation of concerns: ArtStore - файловое хранилище, не Identity Management система
- Industry standard: все enterprise приложения (Jira, GitLab, Jenkins) используют LDAP read-only

## Dual User Store Pattern

### Local Users (source=LOCAL)
```yaml
управление: Admin Module PostgreSQL
операции:
  - ✅ Full CRUD (Create, Read, Update, Delete)
  - ✅ Password management (change, reset, recovery)
  - ✅ Role assignment (ADMIN, OPERATOR, USER)
использование:
  - Development и testing
  - Service accounts
  - Пользователи без LDAP аккаунтов
хранение_пароля:
  - bcrypt hash в PostgreSQL
  - password_hash: NOT NULL для LOCAL users
```

### LDAP Users (source=LDAP)
```yaml
управление: Централизованно через LDAP admin tools
операции_Admin_Module:
  - ✅ Read-only access (bind + search)
  - ✅ Authentication через live LDAP bind
  - ✅ Периодическая синхронизация metadata
  - ✅ Group membership sync
  - ✅ Group → Role mapping
  - ✅ User self-service password change (user меняет свой пароль)
  - ❌ NO admin CRUD operations
  - ❌ NO admin password resets
  - ❌ NO create/delete users в LDAP
хранение_пароля:
  - ❌ НИКОГДА не кешируется локально
  - password_hash: NULL для LDAP users
  - Аутентификация ВСЕГДА через live LDAP bind
```

## Ответы на ключевые вопросы

### 1. Периодическая синхронизация

**Конфигурация:**
```yaml
ldap:
  sync:
    enabled: true
    interval_minutes: 15  # Настраивается в config
    on_startup: true      # Sync при старте приложения
```

**Что синхронизируется:**
- ✅ Username, email, firstname, lastname (metadata)
- ✅ Group membership (memberOf attribute)
- ✅ User status (active в ou=users vs deleted в ou=dismissed)
- ❌ **Пароли НИКОГДА не синхронизируются**

**Операции синхронизации:**
1. **User Discovery**: Поиск новых пользователей в LDAP
2. **Status Verification**: Проверка удаленных (отсутствующих в search base)
3. **Group Membership Update**: Изменения в LDAP группах
4. **Metadata Refresh**: Обновление email, имен

### 2. Локальное кеширование + аутентификация

**Что кешируется (PostgreSQL):**
```python
class User:
    # Identity
    username: str          # Кешировано
    email: str            # Кешировано
    firstname: str        # Кешировано
    lastname: str         # Кешировано
    
    # LDAP integration
    source: UserSource    # LOCAL или LDAP
    ldap_dn: str | None   # LDAP Distinguished Name
    
    # Role и status
    role: Role            # Mapped из LDAP groups
    status: UserStatus    # ACTIVE, DELETED
    
    # Password ТОЛЬКО для LOCAL users
    password_hash: str | None  # NULL для LDAP users
    
    # Timestamps
    last_sync_at: datetime | None
```

**Аутентификация (КРИТИЧНО):**
```python
async def authenticate_ldap_user(username: str, password: str):
    """
    Аутентификация ВСЕГДА через live LDAP bind
    Пароль НИКОГДА не сохраняется локально
    """
    try:
        # 1. LIVE LDAP bind - проверка пароля
        conn = await ldap_connect()
        user_dn = f"uid={username},ou=users,dc=artstore,dc=local"
        await conn.simple_bind(user_dn, password)  
        # Если пароль неверный - exception
        
        # 2. Получить metadata
        user_attrs = await conn.search(user_dn, 
            attributes=['email', 'cn', 'sn', 'givenName', 'memberOf'])
        
        # 3. Обновить локальный кеш
        user = await update_user_cache(username, user_attrs)
        
        # 4. Генерировать JWT токен
        tokens = generate_jwt_tokens(user)
        # access: 30 minutes, refresh: 7 days
        
        return tokens
        
    except ldap.InvalidCredentials:
        raise AuthenticationError("Invalid credentials")
    except ldap.ServerDown:
        raise ServiceUnavailableError("LDAP server unavailable")
```

**LDAP Offline Resilience:**
```yaml
когда_LDAP_недоступен:
  новый_login:
    статус: ❌ Невозможен (нет способа проверить пароль)
    причина: Пароли не кешируются
  
  существующие_JWT_токены:
    access_token: ✅ Работает (до 30 минут)
    refresh_token: ✅ Работает (до 7 дней)
    API_операции: ✅ Продолжают работать
  
  metadata:
    доступность: ✅ Из локального cache
    актуальность: Последняя успешная sync
  
  impact: Минимальный (пользователи логинятся редко, токены long-lived)
```

### 3. Mixed groups - унификация ролей

**Архитектурное правило:**
```
User Source (LDAP/LOCAL) = способ аутентификации
Role (ADMIN/OPERATOR/USER) = права доступа

Source НЕ влияет на permissions!
```

**Пример 1: Общие роли**
```python
# LDAP пользователи
ivanov = User(username="ivanov", source=LDAP, role=ADMIN)
petrov = User(username="petrov", source=LDAP, role=OPERATOR)

# Local пользователи
admin = User(username="admin", source=LOCAL, role=ADMIN)
test = User(username="test", source=LOCAL, role=USER)

# ivanov (LDAP) и admin (LOCAL) имеют одинаковые ADMIN права
# Source влияет ТОЛЬКО на способ аутентификации
```

**Пример 2: Проектная команда**
```python
project_team = [
    User("ivanov", source=LDAP, role=OPERATOR),   # Может загружать файлы
    User("sidorov", source=LOCAL, role=OPERATOR), # Те же права
    User("test", source=LOCAL, role=USER),        # Может только читать
]

# Permissions проверяются ТОЛЬКО по role, не по source
@require_role(Role.OPERATOR)
async def upload_file(...):
    # ivanov (LDAP) и sidorov (LOCAL) - оба могут выполнить
    pass
```

### 4. Деактивация пользователя

**LDAP структура:**
```ldif
dc=artstore,dc=local
├── ou=users (активные, search base)
│   ├── uid=ivanov
│   └── uid=petrov
├── ou=dismissed (уволенные, за пределами search base)
│   └── uid=sidorov
└── ou=groups
    ├── cn=artstore-admins
    └── cn=artstore-operators
```

**Механизм деактивации:**
```yaml
шаг_1_HR_IT:
  действие: Перемещение user в LDAP
  команда: ldapmodify -modrdn
  откуда: uid=sidorov,ou=users,dc=artstore,dc=local
  куда: uid=sidorov,ou=dismissed,dc=artstore,dc=local

шаг_2_periodic_sync:
  действие: Обнаружение отсутствия в search base
  search_base: ou=users,dc=artstore,dc=local
  результат: sidorov не найден в results
  
шаг_3_update_cache:
  действие: Изменение status в PostgreSQL
  новый_status: UserStatus.DELETED
  логирование: "User sidorov deactivated"

шаг_4_новый_login:
  проверка_cache: status == DELETED → reject
  проверка_LDAP: user not in search base → reject
  результат: ❌ Login невозможен

шаг_5_существующие_токены:
  проблема: JWT токены продолжают работать до expiry
  mitigation: Short access token lifetime (30 min)
  emergency: Token blacklist в Redis для немедленного отзыва
```

## Компоненты системы

### 1. LDAPSyncService (Background Task)
```python
class LDAPSyncService:
    """Периодическая синхронизация с LDAP"""
    
    async def periodic_sync(self):
        """Background task каждые N минут"""
        while True:
            await self.sync_users()
            await self.sync_groups()
            await asyncio.sleep(config.ldap.sync_interval_minutes * 60)
    
    async def sync_users(self):
        """Синхронизация пользователей"""
        # 1. Search LDAP (base: ou=users)
        ldap_users = await self.ldap_search_users()
        
        # 2. Compare с cache
        cached_users = await self.get_ldap_users_from_cache()
        
        # 3. Update statuses
        for cached in cached_users:
            if cached.username not in ldap_users:
                await self.mark_user_deleted(cached.username)
        
        # 4. Add new users
        for ldap_user in ldap_users:
            await self.update_user_cache(ldap_user)
        
        # 5. Update group memberships
        await self.sync_group_memberships()
    
    async def sync_groups(self):
        """Синхронизация group memberships"""
        # Update role mappings based on LDAP groups
        pass
```

### 2. LDAPAuthService (Authentication)
```python
class LDAPAuthService:
    """Аутентификация через LDAP"""
    
    async def authenticate(self, username: str, password: str) -> TokenPair:
        """LIVE LDAP bind для проверки пароля"""
        # 1. Check cache status first
        user = await self.user_repo.get_by_username(username)
        if user and user.status == UserStatus.DELETED:
            raise UserDeactivatedError()
        
        # 2. LIVE LDAP bind
        conn = await self.ldap_connect()
        user_dn = f"uid={username},ou=users,dc=artstore,dc=local"
        await conn.simple_bind(user_dn, password)
        
        # 3. Get user attributes
        attrs = await conn.search(user_dn, 
            attributes=['mail', 'cn', 'sn', 'givenName', 'memberOf'])
        
        # 4. Update cache
        user = await self.update_user_cache(username, attrs)
        
        # 5. Map groups to role
        role = self.group_mapping.map_to_role(attrs['memberOf'])
        user.role = role
        await self.user_repo.update(user)
        
        # 6. Generate JWT tokens
        return self.token_service.generate_tokens(user)
    
    async def change_password(self, username: str, 
                             old_password: str, new_password: str):
        """User self-service password change"""
        # User bind with old password
        conn = await self.ldap_connect()
        user_dn = f"uid={username},ou=users,dc=artstore,dc=local"
        await conn.simple_bind(user_dn, old_password)
        
        # LDAP password modify operation (RFC 3062)
        await conn.modify_password(user_dn, old_password, new_password)
```

### 3. GroupMappingService
```python
class GroupMappingService:
    """Mapping LDAP groups → ArtStore roles"""
    
    def __init__(self, config: LDAPConfig):
        self.mappings = config.role_mappings
        # {
        #   "cn=artstore-admins,ou=groups,dc=artstore,dc=local": Role.ADMIN,
        #   "cn=artstore-operators,ou=groups,dc=artstore,dc=local": Role.OPERATOR,
        #   "cn=artstore-users,ou=groups,dc=artstore,dc=local": Role.USER,
        # }
    
    def map_to_role(self, member_of: List[str]) -> Role:
        """Map LDAP memberOf → ArtStore role"""
        for group_dn in member_of:
            if group_dn in self.mappings:
                return self.mappings[group_dn]
        return Role.USER  # Default role
```

### 4. UserCacheRepository
```python
class UserCacheRepository:
    """Управление локальным cache пользователей"""
    
    async def get_or_create_from_ldap(self, username: str, 
                                      ldap_attrs: dict) -> User:
        """Создать/обновить cache из LDAP"""
        user = await self.get_by_username(username)
        
        if user is None:
            user = User(
                username=username,
                source=UserSource.LDAP,
                ldap_dn=ldap_attrs['dn'],
                status=UserStatus.ACTIVE,
                password_hash=None,  # NULL для LDAP users
            )
        
        # Update metadata
        user.email = ldap_attrs.get('mail')
        user.firstname = ldap_attrs.get('givenName')
        user.lastname = ldap_attrs.get('sn')
        user.last_sync_at = datetime.utcnow()
        
        await self.save(user)
        return user
    
    async def mark_deleted(self, username: str):
        """Пометить пользователя удаленным"""
        user = await self.get_by_username(username)
        if user:
            user.status = UserStatus.DELETED
            await self.save(user)
```

## Конфигурация

### config.yaml
```yaml
ldap:
  enabled: true
  server: "ldap://localhost:1389"
  use_tls: false  # true для production
  
  # Read-only bind для синхронизации
  bind_dn: "cn=readonly,dc=artstore,dc=local"
  bind_password: "${LDAP_READONLY_PASSWORD}"
  
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
      - memberOf
  
  groups:
    base_dn: "ou=groups,dc=artstore,dc=local"
    filter: "(objectClass=groupOfNames)"
    member_attribute: "member"
  
  # Group → Role mapping
  role_mappings:
    "cn=artstore-admins,ou=groups,dc=artstore,dc=local": "ADMIN"
    "cn=artstore-operators,ou=groups,dc=artstore,dc=local": "OPERATOR"
    "cn=artstore-users,ou=groups,dc=artstore,dc=local": "USER"
  
  # Sync settings
  sync:
    enabled: true
    interval_minutes: 15
    on_startup: true
    timeout_seconds: 30
  
  # Password management
  password:
    allow_self_service_change: true   # User может менять свой пароль
    allow_admin_reset: false          # Admin НЕ может сбрасывать LDAP пароли
  
  # Connection settings
  connection:
    timeout_seconds: 10
    pool_size: 5
```

### Environment Variables
```bash
# .env
LDAP_READONLY_PASSWORD=readonly_secret_password
LDAP_SERVER=ldap://ldap.artstore.local:389
LDAP_USE_TLS=true
```

## Database Schema Updates

### models/user.py
```python
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func

class UserSource(str, Enum):
    """Источник пользователя"""
    LOCAL = "local"   # Managed by Admin Module
    LDAP = "ldap"     # Managed by LDAP, read-only

class User(Base):
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Identity
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    firstname = Column(String(100))
    lastname = Column(String(100))
    
    # LDAP integration - NEW FIELDS
    source = Column(SQLEnum(UserSource), nullable=False, default=UserSource.LOCAL)
    ldap_dn = Column(String(500), nullable=True)  # LDAP Distinguished Name
    
    # Password - ТОЛЬКО для LOCAL users
    password_hash = Column(String(255), nullable=True)
    # NULL для LDAP users, NOT NULL для LOCAL users
    
    # Role и status
    role = Column(SQLEnum(Role), nullable=False, default=Role.USER)
    status = Column(SQLEnum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    
    # Security
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)  # NEW: Последняя LDAP sync
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "(source = 'local' AND password_hash IS NOT NULL) OR "
            "(source = 'ldap' AND password_hash IS NULL)",
            name="password_hash_source_check"
        ),
    )
```

### Alembic Migration
```python
# alembic/versions/XXX_add_ldap_support.py

def upgrade():
    # Add new columns
    op.add_column('users', sa.Column('source', 
        sa.Enum('local', 'ldap', name='usersource'), 
        nullable=False, server_default='local'))
    
    op.add_column('users', sa.Column('ldap_dn', 
        sa.String(500), nullable=True))
    
    op.add_column('users', sa.Column('last_sync_at', 
        sa.DateTime, nullable=True))
    
    # Make password_hash nullable
    op.alter_column('users', 'password_hash', 
        nullable=True, existing_type=sa.String(255))
    
    # Add constraint
    op.create_check_constraint(
        'password_hash_source_check',
        'users',
        "(source = 'local' AND password_hash IS NOT NULL) OR "
        "(source = 'ldap' AND password_hash IS NULL)"
    )

def downgrade():
    op.drop_constraint('password_hash_source_check', 'users')
    op.drop_column('users', 'last_sync_at')
    op.drop_column('users', 'ldap_dn')
    op.drop_column('users', 'source')
    op.alter_column('users', 'password_hash', nullable=False)
```

## LDAP Directory Structure

### Base Structure (base-structure.ldif)
```ldif
# Base DN
dn: dc=artstore,dc=local
objectClass: top
objectClass: domain
dc: artstore

# Organizational Units
dn: ou=users,dc=artstore,dc=local
objectClass: organizationalUnit
ou: users
description: Active users

dn: ou=dismissed,dc=artstore,dc=local
objectClass: organizationalUnit
ou: dismissed
description: Dismissed/deactivated users

dn: ou=groups,dc=artstore,dc=local
objectClass: organizationalUnit
ou: groups
description: User groups

# Read-only service account
dn: cn=readonly,dc=artstore,dc=local
objectClass: simpleSecurityObject
objectClass: organizationalRole
cn: readonly
userPassword: readonly_secret_password
description: Read-only account for ArtStore sync

# Groups
dn: cn=artstore-admins,ou=groups,dc=artstore,dc=local
objectClass: groupOfNames
cn: artstore-admins
description: ArtStore Administrators
member: cn=placeholder,dc=artstore,dc=local

dn: cn=artstore-operators,ou=groups,dc=artstore,dc=local
objectClass: groupOfNames
cn: artstore-operators
description: ArtStore Operators
member: cn=placeholder,dc=artstore,dc=local

dn: cn=artstore-users,ou=groups,dc=artstore,dc=local
objectClass: groupOfNames
cn: artstore-users
description: ArtStore Users
member: cn=placeholder,dc=artstore,dc=local
```

### Test Users (test-users.ldif)
```ldif
# Test Admin User
dn: uid=ivanov,ou=users,dc=artstore,dc=local
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
uid: ivanov
cn: Ivan Ivanov
sn: Ivanov
givenName: Ivan
mail: ivanov@artstore.local
userPassword: test123
description: Test administrator

# Add to admin group
dn: cn=artstore-admins,ou=groups,dc=artstore,dc=local
changetype: modify
add: member
member: uid=ivanov,ou=users,dc=artstore,dc=local

# Test Operator User
dn: uid=petrov,ou=users,dc=artstore,dc=local
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
uid: petrov
cn: Petr Petrov
sn: Petrov
givenName: Petr
mail: petrov@artstore.local
userPassword: test123
description: Test operator

# Add to operator group
dn: cn=artstore-operators,ou=groups,dc=artstore,dc=local
changetype: modify
add: member
member: uid=petrov,ou=users,dc=artstore,dc=local

# Test Regular User
dn: uid=sidorov,ou=users,dc=artstore,dc=local
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
uid: sidorov
cn: Sergey Sidorov
sn: Sidorov
givenName: Sergey
mail: sidorov@artstore.local
userPassword: test123
description: Test regular user

# Add to users group
dn: cn=artstore-users,ou=groups,dc=artstore,dc=local
changetype: modify
add: member
member: uid=sidorov,ou=users,dc=artstore,dc=local
```

## API Endpoints Updates

### POST /api/auth/login (Modified)
```python
@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Аутентификация пользователя (LOCAL или LDAP)
    
    - LOCAL user: проверка через bcrypt в PostgreSQL
    - LDAP user: проверка через LIVE LDAP bind
    """
    try:
        tokens = await auth_service.authenticate(
            username=credentials.username,
            password=credentials.password
        )
        return tokens
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail="LDAP service unavailable")
```

### POST /api/users/me/password (New)
```python
@router.post("/me/password")
async def change_own_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    User self-service password change
    
    - LOCAL user: update в PostgreSQL
    - LDAP user: LDAP password modify operation
    """
    if current_user.source == UserSource.LOCAL:
        await auth_service.change_local_password(
            user_id=current_user.id,
            old_password=request.old_password,
            new_password=request.new_password
        )
    elif current_user.source == UserSource.LDAP:
        await auth_service.change_ldap_password(
            username=current_user.username,
            old_password=request.old_password,
            new_password=request.new_password
        )
    
    return {"message": "Password changed successfully"}
```

### GET /api/users (Modified)
```python
@router.get("/", response_model=List[UserResponse])
async def list_users(
    source: Optional[UserSource] = None,  # NEW: filter by source
    status: Optional[UserStatus] = None,
    current_user: User = Depends(require_role(Role.ADMIN))
):
    """
    Список пользователей с фильтрацией
    
    Query params:
    - source: local|ldap (опционально)
    - status: active|inactive|locked|deleted (опционально)
    """
    users = await user_service.list_users(source=source, status=status)
    return users
```

### POST /api/ldap/sync (New)
```python
@router.post("/ldap/sync")
async def trigger_ldap_sync(
    current_user: User = Depends(require_role(Role.ADMIN)),
    ldap_sync: LDAPSyncService = Depends(get_ldap_sync_service)
):
    """
    Manual trigger LDAP синхронизации
    
    Только для ADMIN
    """
    result = await ldap_sync.sync_users()
    return {
        "message": "LDAP sync completed",
        "added": result.added_count,
        "updated": result.updated_count,
        "deleted": result.deleted_count,
        "errors": result.errors
    }
```

## Security Considerations

### Password Security
```yaml
LOCAL_users:
  хранение: bcrypt hash в PostgreSQL
  алгоритм: bcrypt (cost factor 12)
  соль: Уникальная для каждого пароля
  
LDAP_users:
  хранение: ❌ НИКОГДА не хранится в Admin Module
  проверка: LIVE LDAP bind при каждом login
  cache: ❌ НЕТ кеша паролей
```

### LDAP Connection Security
```yaml
production:
  protocol: ldaps:// (LDAP over TLS)
  port: 636
  certificate_validation: true
  min_tls_version: "1.2"
  
development:
  protocol: ldap:// (plain)
  port: 389
  use_starttls: false
```

### JWT Token Security
```yaml
access_token:
  lifetime: 30 minutes
  algorithm: RS256
  claims: [sub, username, email, role, type, iat, exp, nbf]
  
refresh_token:
  lifetime: 7 days
  algorithm: RS256
  claims: [sub, username, type, iat, exp, nbf]
  
revocation:
  normal: Wait for expiry (30 min max)
  emergency: Token blacklist в Redis
```

### LDAP Bind Security
```yaml
read_only_account:
  purpose: Синхронизация и поиск
  dn: "cn=readonly,dc=artstore,dc=local"
  permissions: READ only на ou=users, ou=groups
  
user_bind:
  purpose: Аутентификация и self-service password change
  dn: "uid={username},ou=users,dc=artstore,dc=local"
  permissions: Может менять только СВОЙ пароль
  
admin_bind:
  status: ❌ НЕТ admin bind в Admin Module
  rationale: Принцип наименьших привилегий
```

## Implementation Checklist

### Phase 1: Database и Models
- [ ] Создать Alembic migration для LDAP полей
- [ ] Обновить User model (source, ldap_dn, last_sync_at)
- [ ] Добавить constraint для password_hash
- [ ] Протестировать migration на dev БД

### Phase 2: LDAP Infrastructure
- [ ] Создать base-structure.ldif
- [ ] Создать test-users.ldif
- [ ] Загрузить в 389 Directory Server
- [ ] Протестировать LDAP структуру

### Phase 3: Core Services
- [ ] Реализовать LDAPConnectionPool
- [ ] Реализовать LDAPAuthService
- [ ] Реализовать LDAPSyncService
- [ ] Реализовать GroupMappingService
- [ ] Добавить в AuthService диспетчеризацию LOCAL vs LDAP

### Phase 4: API Endpoints
- [ ] Модифицировать POST /api/auth/login
- [ ] Добавить POST /api/users/me/password
- [ ] Модифицировать GET /api/users (добавить source filter)
- [ ] Добавить POST /api/ldap/sync

### Phase 5: Background Tasks
- [ ] Реализовать periodic sync task
- [ ] Добавить в startup приложения
- [ ] Настроить error handling и retry logic
- [ ] Добавить метрики синхронизации

### Phase 6: Configuration
- [ ] Добавить LDAP секцию в config.yaml
- [ ] Добавить environment variables
- [ ] Создать config validation
- [ ] Документировать конфигурацию

### Phase 7: Testing
- [ ] Unit tests для LDAPAuthService
- [ ] Unit tests для LDAPSyncService
- [ ] Integration tests с реальным LDAP
- [ ] E2E tests для login flow
- [ ] Performance tests синхронизации

### Phase 8: Documentation
- [ ] API documentation (OpenAPI/Swagger)
- [ ] LDAP setup guide
- [ ] Troubleshooting guide
- [ ] Security best practices

## Risks and Mitigations

### Risk 1: LDAP Unavailability
```yaml
риск: LDAP server down → users cannot login
вероятность: Medium (зависит от LDAP infrastructure)
impact: High (authentication blocked)

mitigation:
  - Long-lived JWT refresh tokens (7 days)
  - Local cache для metadata
  - Monitoring и alerting LDAP health
  - Fallback: Emergency local admin account
```

### Risk 2: Token Revocation Delay
```yaml
риск: Уволенный пользователь может работать до 30 min (access token lifetime)
вероятность: Medium
impact: Medium (ограниченное время)

mitigation:
  - Short access token lifetime (30 min)
  - Immediate check status при refresh
  - Emergency: Token blacklist в Redis
  - Monitoring подозрительной активности
```

### Risk 3: LDAP Credential Leak
```yaml
риск: Readonly LDAP password скомпрометирован
вероятность: Low
impact: Medium (только read access)

mitigation:
  - Readonly account имеет только READ права
  - Credential rotation policy (каждые 90 дней)
  - Secrets management (не hardcode в config)
  - Audit logging LDAP access
```

### Risk 4: Sync Delays
```yaml
риск: Изменения в LDAP не сразу отражаются в ArtStore
вероятность: High
impact: Low (temporary inconsistency)

mitigation:
  - Configurable sync interval (default 15 min)
  - Manual sync trigger для admins
  - Real-time update при login
  - Acceptable для business (не критично)
```

## Success Criteria

### Functional
- ✅ Local users работают как раньше (backward compatibility)
- ✅ LDAP users могут логиниться через corporate credentials
- ✅ Group memberships правильно mapped на roles
- ✅ Periodic sync обновляет user cache
- ✅ User может менять свой LDAP пароль
- ✅ Деактивированные users не могут логиниться

### Security
- ✅ LDAP пароли НИКОГДА не хранятся локально
- ✅ Admin Module имеет только read-only LDAP access
- ✅ Readonly LDAP credentials защищены (environment variables)
- ✅ JWT tokens используют RS256 asymmetric encryption
- ✅ Audit logging всех authentication events

### Performance
- ✅ Login latency < 2 seconds (with live LDAP bind)
- ✅ LDAP sync завершается за < 1 minute для 1000 users
- ✅ Token validation < 10ms (local public key)
- ✅ Cache hit rate > 95% для metadata queries

### Operational
- ✅ LDAP downtime не блокирует существующие sessions
- ✅ Monitoring и alerting настроены
- ✅ Documentation complete
- ✅ Rollback plan готов

## References

### Standards
- **RFC 4511**: LDAP Protocol
- **RFC 3062**: LDAP Password Modify Extended Operation
- **RFC 7519**: JSON Web Token (JWT)
- **RFC 7515**: JSON Web Signature (JWS) - RS256

### Tools
- **389 Directory Server**: LDAP сервер в проекте
- **python-ldap**: Python LDAP client library
- **ldap3**: Alternative async LDAP client
- **PyJWT**: JWT implementation

### Best Practices
- OWASP Authentication Cheat Sheet
- NIST SP 800-63B: Digital Identity Guidelines
- CIS LDAP Benchmark
- Enterprise LDAP Integration Patterns
