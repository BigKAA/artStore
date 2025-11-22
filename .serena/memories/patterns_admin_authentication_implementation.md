# Pattern: Admin Authentication Implementation

**Domain**: Authentication & Authorization  
**Technology**: FastAPI + JWT + PostgreSQL + SQLAlchemy 2.0  
**Last Updated**: 2025-11-17

## Pattern Overview

Complete admin authentication system with JWT tokens, RBAC, password security, and audit logging for administrative interfaces.

## Core Components

### 1. Database Schema Pattern

**PostgreSQL Enum Type**:
```python
# In Alembic migration
admin_role_enum = postgresql.ENUM(
    'super_admin', 'admin', 'readonly',
    name='admin_role',
    create_type=True  # Let SQLAlchemy handle enum creation
)
```

**Admin Users Table**:
```python
op.create_table(
    'admin_users',
    sa.Column('id', sa.Uuid(), nullable=False, default=uuid.uuid4),
    sa.Column('username', sa.String(100), nullable=False),
    sa.Column('email', sa.String(255), nullable=False),
    sa.Column('password_hash', sa.String(255), nullable=False),
    sa.Column('password_history', sa.JSON(), nullable=True),  # Last 5 passwords
    sa.Column('password_changed_at', sa.DateTime(timezone=True)),
    sa.Column('role', admin_role_enum, nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default='true'),
    sa.Column('is_system', sa.Boolean(), server_default='false'),
    sa.Column('login_attempts', sa.Integer(), server_default='0'),
    sa.Column('locked_until', sa.DateTime(timezone=True)),
    sa.UniqueConstraint('username'),
    sa.UniqueConstraint('email')
)
```

### 2. SQLAlchemy Model Pattern

**Enum Mapping** (CRITICAL):
```python
from sqlalchemy import Enum as SQLEnum

class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    READONLY = "readonly"

class AdminUser(Base):
    role: Mapped[AdminRole] = mapped_column(
        SQLEnum(
            AdminRole, 
            name="admin_role",
            native_enum=True,  # Use PostgreSQL native enum
            values_callable=lambda x: [e.value for e in x]  # Map to string values
        ),
        nullable=False,
        default=AdminRole.ADMIN
    )
```

**Why**: SQLAlchemy 2.0 doesn't automatically convert Python enum members to their string values for PostgreSQL. The `values_callable` parameter explicitly extracts `.value` from each enum member.

### 3. Password Security Pattern

**Hashing**:
```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(self, password: str) -> str:
    return self.pwd_context.hash(password)

def verify_password(self, plain_password: str, hashed_password: str) -> bool:
    return self.pwd_context.verify(plain_password, hashed_password)
```

**Password History**:
```python
def add_to_password_history(self, password_hash: str, max_history: int = 5):
    history = self.password_history or []
    history.insert(0, password_hash)
    self.password_history = history[:max_history]
    self.password_changed_at = datetime.now(timezone.utc)

def is_password_in_history(self, password: str) -> bool:
    if not self.password_history:
        return False
    return any(
        self.pwd_context.verify(password, old_hash) 
        for old_hash in self.password_history
    )
```

**Account Locking**:
```python
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=30)

def is_locked(self) -> bool:
    if not self.locked_until:
        return False
    return datetime.now(timezone.utc) < self.locked_until

async def _handle_failed_login(self, db: AsyncSession, admin_user: AdminUser):
    admin_user.login_attempts += 1
    
    if admin_user.login_attempts >= MAX_LOGIN_ATTEMPTS:
        admin_user.locked_until = datetime.now(timezone.utc) + LOCKOUT_DURATION
        logger.warning(f"Account locked: {admin_user.username}")
    
    await db.commit()
```

### 4. JWT Token Pattern

**Generic Token Creation**:
```python
def create_token_from_data(
    self,
    data: Dict,
    expires_delta: timedelta,
    token_type: str = "access"
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    claims = {
        **data,
        "iat": now,
        "exp": expire,
        "nbf": now
    }

    return jwt.encode(claims, private_key, algorithm="RS256")
```

**Admin Token Claims**:
```python
def _create_tokens(self, admin_user: AdminUser) -> Tuple[str, str]:
    # Access token (30 minutes)
    access_data = {
        "sub": admin_user.username,
        "type": "admin_user",  # Type discrimination
        "role": admin_user.role.value,
        "email": admin_user.email
    }
    access_token = self.token_service.create_token_from_data(
        access_data,
        timedelta(minutes=30),
        "access"
    )

    # Refresh token (7 days)
    refresh_data = {
        "sub": admin_user.username,
        "type": "admin_user"
    }
    refresh_token = self.token_service.create_token_from_data(
        refresh_data,
        timedelta(days=7),
        "refresh"
    )

    return access_token, refresh_token
```

### 5. Security Dependency Pattern

**JWT Validation**:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_admin_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: AsyncSession = Depends(get_db)
) -> AdminUser:
    token = credentials.credentials
    
    # Decode and validate JWT
    payload = token_service.decode_token(token)
    
    # Check token type
    if payload.get("type") != "admin_user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid token type: expected admin_user"
        )
    
    # Get admin user from database
    username = payload.get("sub")
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == username)
    )
    admin_user = result.scalar_one_or_none()
    
    if not admin_user or not admin_user.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or disabled account"
        )
    
    return admin_user
```

**RBAC Dependency**:
```python
def require_role(*allowed_roles: AdminRole):
    async def role_checker(
        current_admin: AdminUser = Depends(get_current_admin_user)
    ) -> AdminUser:
        if current_admin.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires {allowed_roles}"
            )
        return current_admin
    
    return role_checker
```

### 6. API Endpoint Pattern

**Login Endpoint**:
```python
@router.post("/login", response_model=AdminTokenResponse)
async def login(
    credentials: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
    auth_service: AdminAuthService = Depends(get_admin_auth_service)
) -> AdminTokenResponse:
    try:
        access_token, refresh_token = await auth_service.authenticate(
            db=db,
            username=credentials.username,
            password=credentials.password
        )
        
        return AdminTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=1800
        )
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
```

**Protected Endpoint**:
```python
@router.get("/me", response_model=AdminUserResponse)
async def get_current_user(
    current_admin: AdminUser = Depends(get_current_admin_user)
) -> AdminUserResponse:
    return AdminUserResponse(
        id=current_admin.id,
        username=current_admin.username,
        email=current_admin.email,
        role=current_admin.role,
        enabled=current_admin.enabled,
        last_login_at=current_admin.last_login_at
    )
```

**Role-Protected Endpoint**:
```python
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    # Only SUPER_ADMIN can delete users
    pass
```

### 7. Initial Admin Creation Pattern

```python
async def create_initial_admin_user(settings: Settings, db: AsyncSession):
    # Check if any admin users exist
    result = await db.execute(select(func.count()).select_from(AdminUser))
    if result.scalar() > 0:
        return
    
    # Hash default password
    admin_auth_service = AdminAuthService()
    password_hash = admin_auth_service.hash_password("admin123")
    
    # Create initial admin
    initial_admin = AdminUser(
        username="admin",
        email="admin@artstore.local",
        password_hash=password_hash,
        role=AdminRole.SUPER_ADMIN,
        enabled=True,
        is_system=True  # Cannot be deleted via API
    )
    
    db.add(initial_admin)
    await db.commit()
    
    # Log security warning
    logger.warning(
        "SECURITY AUDIT: Initial admin user created with default password. "
        "Please change immediately!",
        extra={"security_risk": "high"}
    )
```

## Common Issues and Solutions

### Issue 1: Bcrypt Compatibility
**Problem**: "password cannot be longer than 72 bytes"  
**Cause**: passlib 1.7.4 incompatible with latest bcrypt on Python 3.12  
**Solution**: Pin `bcrypt==4.1.2` in requirements.txt

### Issue 2: Enum Value Mismatch
**Problem**: "invalid input value for enum: 'SUPER_ADMIN'"  
**Cause**: SQLAlchemy not converting enum members to string values  
**Solution**: Use `native_enum=True, values_callable=lambda x: [e.value for e in x]`

### Issue 3: Token Type Confusion
**Problem**: Admin tokens accepted for service account endpoints  
**Cause**: No token type discrimination  
**Solution**: Add "type" claim to JWT and validate in dependencies

## Security Checklist

- [ ] Password hashing with bcrypt (work factor ≥12)
- [ ] Password history tracking (minimum 5 passwords)
- [ ] Password complexity validation (length, charset, strength)
- [ ] Account locking after failed attempts (5 attempts, 30 min lockout)
- [ ] JWT token expiration (access: 30 min, refresh: 7 days)
- [ ] Token type discrimination in claims
- [ ] RBAC enforcement on protected endpoints
- [ ] System admin protection (is_system flag)
- [ ] Audit logging for authentication events
- [ ] Security warnings for default credentials
- [ ] HTTPS/TLS for token transmission
- [ ] Token blacklist for logout (TODO)

## Performance Considerations

- Index on username and email for fast lookups
- Index on role for RBAC queries
- Index on enabled for filtering active accounts
- JWT validation without database lookup (public key verification)
- Password history limited to 5 entries

## Testing Checklist

- [ ] Successful login with valid credentials
- [ ] Failed login with invalid credentials
- [ ] Account locking after 5 failed attempts
- [ ] Account unlock after lockout duration
- [ ] Password change with validation
- [ ] Password history enforcement
- [ ] Token refresh flow
- [ ] Token expiration handling
- [ ] RBAC enforcement for protected endpoints
- [ ] System admin deletion protection
- [ ] Initial admin creation on empty database
