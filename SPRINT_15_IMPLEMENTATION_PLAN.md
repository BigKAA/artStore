# Sprint 15 Implementation Plan: Security Hardening Phase 1-3

**Sprint Duration**: Week 15 (2025-11-16 → 2025-11-30)
**Status**: PLANNED
**Priority**: P1 (CRITICAL для production)
**Complexity**: MEDIUM-HIGH

---

## Executive Summary

Sprint 15 реализует **5 из 7 критических (MUST HAVE)** security fixes, выявленных в Sprint 14 Security Audit:

1. ✅ **CORS Whitelist Configuration** (Phase 1)
2. ✅ **Strong Random Passwords** (Phase 1)
3. ✅ **JWT Key Rotation Automation** (Phase 2)
4. ✅ **Comprehensive Audit Logging** (Phase 2)
5. ✅ **Docker Secrets Management** (Phase 3)

**Deferred to Sprint 16**:
- ❌ TLS 1.3 Configuration (высокая сложность, требует certificate infrastructure)
- ❌ mTLS Inter-Service Communication (высокая сложность, architectural changes)

**Expected Security Score**: 6/10 → 8/10 (+33% improvement)

---

## Phase 1: Quick Security Wins (Week 15.1)

**Duration**: 1-2 дня
**Priority**: P1
**Complexity**: LOW

### 1.1 CORS Whitelist Configuration

**Objective**: Заменить `allow_origins=["*"]` на explicit whitelist во всех модулях для защиты от CSRF attacks.

#### Implementation Steps

**Step 1: Audit Current CORS Configuration**
```bash
# Search for CORS configuration in all modules
grep -r "allow_origins" admin-module/ storage-element/ ingester-module/ query-module/
```

**Expected Findings**:
- `admin-module/app/main.py`: CORSMiddleware with `allow_origins=["*"]`
- Similar patterns в других модулях

**Step 2: Create CORS Settings in Configuration**

**File**: `admin-module/app/core/settings.py`
```python
class CORSSettings(BaseModel):
    """CORS configuration settings."""

    allowed_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:4200"],  # Default для development
        description="List of allowed CORS origins"
    )

    allowed_origins_regex: Optional[str] = Field(
        default=None,
        description="Regex pattern for allowed origins (optional)"
    )

    allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )

    allowed_methods: List[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        description="Allowed HTTP methods"
    )

    allowed_headers: List[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed request headers"
    )

    expose_headers: List[str] = Field(
        default_factory=lambda: [],
        description="Headers exposed to browser"
    )

    max_age: int = Field(
        default=600,
        description="Max age for preflight cache (seconds)"
    )

    @field_validator("allowed_origins")
    @classmethod
    def validate_no_wildcards(cls, v: List[str]) -> List[str]:
        """Ensure no wildcard origins in production."""
        if "*" in v:
            import os
            env = os.getenv("ENVIRONMENT", "development")
            if env == "production":
                raise ValueError("Wildcard CORS origins not allowed in production")
        return v

class Settings(BaseModel):
    # ... existing settings ...
    cors: CORSSettings = Field(default_factory=CORSSettings)
```

**Step 3: Update Main.py CORS Middleware**

**File**: `admin-module/app/main.py`
```python
from fastapi.middleware.cors import CORSMiddleware

# Replace existing CORSMiddleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.allowed_origins,
    allow_origin_regex=settings.cors.allowed_origins_regex,
    allow_credentials=settings.cors.allow_credentials,
    allow_methods=settings.cors.allowed_methods,
    allow_headers=settings.cors.allowed_headers,
    expose_headers=settings.cors.expose_headers,
    max_age=settings.cors.max_age,
)
```

**Step 4: Environment Variables Configuration**

**File**: `admin-module/.env.example`
```bash
# CORS Configuration
CORS_ALLOWED_ORIGINS=["http://localhost:4200","http://localhost:3000"]  # Development origins
# For production, use explicit domains:
# CORS_ALLOWED_ORIGINS=["https://admin.artstore.example.com","https://app.artstore.example.com"]

# Optional: regex pattern for dynamic subdomains
# CORS_ALLOWED_ORIGINS_REGEX=https://.*\.artstore\.example\.com
```

**Step 5: Apply to All Modules**
- Repeat Steps 2-4 для: `storage-element`, `ingester-module`, `query-module`
- Ensure consistent configuration across all services

**Step 6: Testing**
```bash
# Test CORS with allowed origin (should succeed)
curl -X OPTIONS http://localhost:8000/api/v1/auth/token \
  -H "Origin: http://localhost:4200" \
  -H "Access-Control-Request-Method: POST" \
  -v

# Test CORS with disallowed origin (should fail)
curl -X OPTIONS http://localhost:8000/api/v1/auth/token \
  -H "Origin: http://malicious-site.com" \
  -H "Access-Control-Request-Method: POST" \
  -v
```

**Expected Results**:
- Allowed origin: `Access-Control-Allow-Origin: http://localhost:4200`
- Disallowed origin: No `Access-Control-Allow-Origin` header

**Files Modified**:
- `admin-module/app/core/settings.py` (+50 lines)
- `admin-module/app/main.py` (~10 lines modified)
- `admin-module/.env.example` (+5 lines)
- Repeat for 3 other modules = **12 files total**

**Validation**:
- [ ] CORS configured in all 4 modules
- [ ] No wildcard origins in configuration
- [ ] Environment variables documented
- [ ] CORS tests passing for allowed/disallowed origins
- [ ] Prometheus metrics tracking CORS rejections (optional)

---

### 1.2 Strong Random Passwords

**Objective**: Заменить все default weak passwords на cryptographically secure random passwords.

#### Implementation Steps

**Step 1: Create Password Generation Script**

**File**: `scripts/generate_secrets.sh` (NEW)
```bash
#!/bin/bash
# generate_secrets.sh - Generate secure random passwords for all services

set -e

echo "Generating secure random passwords..."

# Function to generate random password
generate_password() {
    local length=$1
    local charset="A-Za-z0-9!@#$%^&*()-_=+[]{}|;:,.<>?"

    # Use /dev/urandom for cryptographically secure random
    LC_ALL=C tr -dc "$charset" < /dev/urandom | head -c "$length"
}

# PostgreSQL password (32 chars)
POSTGRES_PASSWORD=$(generate_password 32)
echo "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}"

# Redis password (32 chars)
REDIS_PASSWORD=$(generate_password 32)
echo "REDIS_PASSWORD=${REDIS_PASSWORD}"

# Grafana admin password (24 chars)
GRAFANA_ADMIN_PASSWORD=$(generate_password 24)
echo "GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}"

# MinIO credentials (optional, if used)
MINIO_ROOT_PASSWORD=$(generate_password 32)
echo "MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}"

echo ""
echo "✅ Passwords generated successfully!"
echo "⚠️  IMPORTANT: Save these passwords securely (password manager, secrets vault)"
echo "⚠️  DO NOT commit .env file with real passwords to git"
echo ""
echo "To use these passwords:"
echo "1. Copy output to .env file in project root"
echo "2. Restart all services: docker-compose down && docker-compose up -d"
```

**Step 2: Make Script Executable**
```bash
chmod +x scripts/generate_secrets.sh
```

**Step 3: Update docker-compose.yml**

**File**: `docker-compose.yml`
```yaml
services:
  postgres:
    environment:
      - POSTGRES_USER=artstore
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}  # From .env
      # Remove hardcoded: POSTGRES_PASSWORD=password

  redis:
    command: redis-server --requirepass ${REDIS_PASSWORD}  # From .env

  # ... other services ...
```

**File**: `docker-compose.monitoring.yml`
```yaml
services:
  grafana:
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GF_SECURITY_ADMIN_PASSWORD}  # From .env
      # Remove hardcoded: GF_SECURITY_ADMIN_PASSWORD=admin123
```

**Step 4: Create .env Template**

**File**: `.env.example` (UPDATE)
```bash
# =============================================================================
# ArtStore Environment Configuration Template
# =============================================================================
#
# SECURITY WARNING:
# - DO NOT use these default values in production
# - Generate strong random passwords with: ./scripts/generate_secrets.sh
# - Store real passwords in .env file (git-ignored)
# - Never commit .env file to version control
#
# =============================================================================

# PostgreSQL Configuration
POSTGRES_USER=artstore
POSTGRES_PASSWORD=REPLACE_WITH_STRONG_RANDOM_PASSWORD_32_CHARS
POSTGRES_DB=artstore
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=REPLACE_WITH_STRONG_RANDOM_PASSWORD_32_CHARS

# Grafana Configuration (Monitoring)
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=REPLACE_WITH_STRONG_RANDOM_PASSWORD_24_CHARS

# MinIO Configuration (Object Storage)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=REPLACE_WITH_STRONG_RANDOM_PASSWORD_32_CHARS

# Application Environment
ENVIRONMENT=development  # development | staging | production
DEBUG=true  # Set to false in production
LOG_LEVEL=INFO
```

**Step 5: Update .gitignore**

**File**: `.gitignore` (UPDATE)
```gitignore
# Environment variables with secrets
.env
.env.local
.env.*.local

# Keep templates in git
!.env.example
```

**Step 6: Documentation Update**

**File**: `docs/SECURITY_SETUP.md` (NEW)
```markdown
# Security Setup Guide

## Password Generation

### Quick Start
```bash
# Generate all passwords
./scripts/generate_secrets.sh > .env

# Review generated passwords
cat .env

# Restart services with new passwords
docker-compose down
docker-compose up -d
```

### Manual Password Generation
If you prefer to generate passwords manually:

```bash
# PostgreSQL password (32 chars)
openssl rand -base64 24

# Redis password (32 chars)
openssl rand -base64 24

# Grafana password (24 chars)
openssl rand -base64 18
```

### Password Requirements

- **PostgreSQL**: Minimum 32 characters, alphanumeric + symbols
- **Redis**: Minimum 32 characters, alphanumeric + symbols
- **Grafana**: Minimum 24 characters, alphanumeric + symbols
- **MinIO**: Minimum 32 characters, alphanumeric

### Password Rotation Schedule

- **PostgreSQL**: Every 90 days
- **Redis**: Every 90 days
- **Grafana**: Every 90 days
- **JWT Keys**: Every 24 hours (automated)

### Secure Storage

- Use password manager (1Password, LastPass, Bitwarden)
- OR use secrets management system (HashiCorp Vault, AWS Secrets Manager)
- Never store passwords in plain text files committed to git
- Backup .env file securely (encrypted backup)
```

**Step 7: Testing**
```bash
# Generate passwords
./scripts/generate_secrets.sh > .env

# Verify .env created
cat .env

# Test PostgreSQL connection with new password
docker-compose up -d postgres
docker exec -it artstore_postgres psql -U artstore -d artstore
# Enter password from .env

# Test Redis connection with new password
docker-compose up -d redis
docker exec -it artstore_redis redis-cli
# AUTH <password from .env>

# Test Grafana login
docker-compose -f docker-compose.monitoring.yml up -d grafana
# Open http://localhost:3000
# Login with admin / <password from .env>
```

**Files Created/Modified**:
- `scripts/generate_secrets.sh` (NEW, 50 lines)
- `docker-compose.yml` (MODIFIED, remove hardcoded passwords)
- `docker-compose.monitoring.yml` (MODIFIED, remove hardcoded passwords)
- `.env.example` (UPDATE, +30 lines with security warnings)
- `.gitignore` (UPDATE, ensure .env excluded)
- `docs/SECURITY_SETUP.md` (NEW, 100 lines)

**Validation**:
- [ ] Password generation script working
- [ ] .env file excluded from git
- [ ] All services start with new passwords
- [ ] Documentation complete with rotation schedule
- [ ] No hardcoded passwords in docker-compose files

---

**Phase 1 Deliverables**:
- ✅ CORS configured with explicit whitelists (4 modules)
- ✅ Strong random passwords generated and documented
- ✅ Password generation automation
- ✅ Security setup documentation
- **Files Modified**: 12
- **Files Created**: 3
- **Lines Added**: ~200
- **Security Score**: 6/10 → 6.5/10 (+8%)

---

## Phase 2: Authentication & Logging (Week 15.2)

**Duration**: 3-5 дней
**Priority**: P1
**Complexity**: MEDIUM-HIGH

### 2.1 JWT Key Rotation Automation

**Objective**: Автоматическая ротация JWT ключей каждые 24 часа с graceful transition period.

#### Architecture Design

**Components**:
1. **KeyRotationScheduler**: Background task для автоматической ротации
2. **KeyVersioning**: PostgreSQL table для хранения key versions
3. **GracefulTransition**: Поддержка старого + нового ключа в течение 1 часа
4. **DistributedLock**: Redis coordination для cluster safety
5. **Metrics**: Prometheus tracking rotation events

#### Implementation Steps

**Step 1: Create Database Migration**

**File**: `admin-module/alembic/versions/XXXXXX_add_jwt_key_versioning.py` (NEW)
```python
"""Add JWT key versioning table

Revision ID: XXXXXX
Revises: YYYYYY
Create Date: 2025-11-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'XXXXXX'
down_revision = 'YYYYYY'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'jwt_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version', sa.String(36), unique=True, nullable=False, index=True),
        sa.Column('private_key', sa.Text(), nullable=False),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('algorithm', sa.String(10), nullable=False, default='RS256'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False, index=True),
        sa.Column('rotation_count', sa.Integer(), default=0, nullable=False),
        schema=None
    )

    # Index for efficient key lookup
    op.create_index('idx_jwt_keys_active_version', 'jwt_keys', ['is_active', 'version'])

def downgrade():
    op.drop_index('idx_jwt_keys_active_version', table_name='jwt_keys')
    op.drop_table('jwt_keys')
```

**Step 2: Create JWT Key Model**

**File**: `admin-module/app/models/jwt_key.py` (NEW)
```python
"""JWT Key versioning model."""
from datetime import datetime, timedelta
from typing import Optional
import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base_class import Base


class JWTKey(Base):
    """JWT key version for rotation support."""

    __tablename__ = "jwt_keys"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    private_key = Column(Text, nullable=False)
    public_key = Column(Text, nullable=False)
    algorithm = Column(String(10), nullable=False, default="RS256")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    rotation_count = Column(Integer, default=0, nullable=False)

    @classmethod
    def create_new_key(cls, session, validity_hours: int = 25) -> "JWTKey":
        """
        Create new JWT key pair with specified validity.

        Args:
            session: Database session
            validity_hours: Key validity in hours (default 25h = 24h + 1h grace period)

        Returns:
            JWTKey: New key instance
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        # Generate RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Serialize private key
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        # Serialize public key
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        # Create database record
        expires_at = datetime.utcnow() + timedelta(hours=validity_hours)

        jwt_key = cls(
            private_key=private_pem,
            public_key=public_pem,
            expires_at=expires_at,
            is_active=True,
            rotation_count=0
        )

        session.add(jwt_key)
        session.commit()
        session.refresh(jwt_key)

        return jwt_key

    @classmethod
    def get_active_keys(cls, session) -> list["JWTKey"]:
        """Get all currently active keys (for validation)."""
        now = datetime.utcnow()
        return session.query(cls).filter(
            cls.is_active == True,
            cls.expires_at > now
        ).order_by(cls.created_at.desc()).all()

    @classmethod
    def get_current_signing_key(cls, session) -> Optional["JWTKey"]:
        """Get most recent active key for signing new tokens."""
        active_keys = cls.get_active_keys(session)
        return active_keys[0] if active_keys else None

    def deactivate(self, session):
        """Mark key as inactive (soft delete)."""
        self.is_active = False
        session.commit()
```

**(Продолжение в следующем сообщении из-за ограничений длины...)**

**Step 3: Create Key Rotation Service**

**File**: `admin-module/app/services/jwt_rotation.py` (NEW)
```python
"""JWT key rotation service with distributed locking."""
import logging
from datetime import datetime, timedelta
from typing import Optional

import redis
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.jwt_key import JWTKey

logger = logging.getLogger(__name__)
settings = get_settings()


class JWTKeyRotationService:
    """Service for automatic JWT key rotation."""

    LOCK_KEY = "jwt_key_rotation_lock"
    LOCK_TIMEOUT = 300  # 5 minutes

    def __init__(self, db_session: Session, redis_client: redis.Redis):
        self.db = db_session
        self.redis = redis_client

    def should_rotate(self) -> bool:
        """Check if key rotation is needed."""
        current_key = JWTKey.get_current_signing_key(self.db)

        if not current_key:
            logger.warning("No active JWT key found, rotation needed")
            return True

        # Rotate 1 hour before expiry
        rotation_threshold = current_key.expires_at - timedelta(hours=1)
        needs_rotation = datetime.utcnow() >= rotation_threshold

        if needs_rotation:
            logger.info(f"Key rotation needed: current key expires at {current_key.expires_at}")

        return needs_rotation

    def acquire_lock(self) -> bool:
        """Acquire distributed lock for rotation (cluster-safe)."""
        return self.redis.set(
            self.LOCK_KEY,
            "locked",
            nx=True,  # Only set if not exists
            ex=self.LOCK_TIMEOUT  # Auto-expire after 5 minutes
        )

    def release_lock(self):
        """Release distributed lock."""
        self.redis.delete(self.LOCK_KEY)

    def rotate_keys(self) -> JWTKey:
        """
        Perform key rotation with graceful transition.

        Returns:
            JWTKey: Newly created key

        Raises:
            RuntimeError: If lock cannot be acquired or rotation fails
        """
        # Acquire distributed lock
        if not self.acquire_lock():
            raise RuntimeError("Failed to acquire rotation lock - another instance may be rotating")

        try:
            logger.info("Starting JWT key rotation...")

            # Create new key (25 hours validity = 24h + 1h grace period)
            new_key = JWTKey.create_new_key(self.db, validity_hours=25)
            logger.info(f"Created new JWT key version: {new_key.version}")

            # Deactivate old expired keys (keep 1h for grace period)
            old_keys = self.db.query(JWTKey).filter(
                JWTKey.expires_at < datetime.utcnow()
            ).all()

            for old_key in old_keys:
                old_key.deactivate(self.db)
                logger.info(f"Deactivated expired key: {old_key.version}")

            # Increment rotation counter
            new_key.rotation_count = len(old_keys)
            self.db.commit()

            logger.info(f"JWT key rotation complete. Active keys: {len(JWTKey.get_active_keys(self.db))}")

            return new_key

        except Exception as e:
            logger.error(f"JWT key rotation failed: {e}")
            self.db.rollback()
            raise

        finally:
            self.release_lock()

    def cleanup_old_keys(self, retention_days: int = 30):
        """Remove old deactivated keys beyond retention period."""
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        old_keys = self.db.query(JWTKey).filter(
            JWTKey.is_active == False,
            JWTKey.created_at < cutoff_date
        ).all()

        for key in old_keys:
            self.db.delete(key)
            logger.info(f"Deleted old key: {key.version} (created {key.created_at})")

        self.db.commit()
        logger.info(f"Cleaned up {len(old_keys)} old keys")
```

**Step 4: Create Background Scheduler**

**File**: `admin-module/app/core/scheduler.py` (NEW)
```python
"""Background scheduler for periodic tasks."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal
from app.core.redis import get_redis_client
from app.services.jwt_rotation import JWTKeyRotationService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def rotate_jwt_keys_job():
    """Background job для JWT key rotation."""
    logger.info("JWT key rotation job started")

    db = SessionLocal()
    redis_client = get_redis_client()

    try:
        rotation_service = JWTKeyRotationService(db, redis_client)

        if rotation_service.should_rotate():
            new_key = rotation_service.rotate_keys()
            logger.info(f"JWT keys rotated successfully. New version: {new_key.version}")
        else:
            logger.debug("JWT key rotation not needed yet")

    except Exception as e:
        logger.error(f"JWT key rotation job failed: {e}", exc_info=True)

    finally:
        db.close()


def cleanup_old_keys_job():
    """Background job для очистки старых ключей."""
    logger.info("Old keys cleanup job started")

    db = SessionLocal()
    redis_client = get_redis_client()

    try:
        rotation_service = JWTKeyRotationService(db, redis_client)
        rotation_service.cleanup_old_keys(retention_days=30)

    except Exception as e:
        logger.error(f"Old keys cleanup job failed: {e}", exc_info=True)

    finally:
        db.close()


def start_scheduler():
    """Start background scheduler with all jobs."""
    # JWT key rotation: every 24 hours at 02:00 UTC
    scheduler.add_job(
        rotate_jwt_keys_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="jwt_key_rotation",
        name="JWT Key Rotation",
        replace_existing=True
    )

    # Old keys cleanup: weekly on Sunday at 03:00 UTC
    scheduler.add_job(
        cleanup_old_keys_job,
        trigger=CronTrigger(day_of_week='sun', hour=3, minute=0),
        id="cleanup_old_keys",
        name="Cleanup Old JWT Keys",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Background scheduler started with jobs: JWT rotation (daily 02:00), Cleanup (weekly Sunday 03:00)")


def shutdown_scheduler():
    """Shutdown background scheduler gracefully."""
    scheduler.shutdown()
    logger.info("Background scheduler shutdown")
```

**Step 5: Update Main Application**

**File**: `admin-module/app/main.py` (MODIFY)
```python
from app.core.scheduler import start_scheduler, shutdown_scheduler

@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Starting ArtStore Admin Module...")

    # ... existing startup code ...

    # Start background scheduler
    start_scheduler()
    logger.info("Background scheduler started")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Shutting down ArtStore Admin Module...")

    # Shutdown background scheduler
    shutdown_scheduler()

    # ... existing shutdown code ...
```

**Step 6: Update JWT Service to Use Key Versioning**

**File**: `admin-module/app/services/auth_service.py` (MODIFY)
```python
from app.models.jwt_key import JWTKey

class AuthService:
    # ... existing code ...

    def generate_token(self, service_account_id: int, role: str) -> str:
        """Generate JWT token using current signing key."""
        # Get current signing key from database
        current_key = JWTKey.get_current_signing_key(self.db)

        if not current_key:
            raise RuntimeError("No active JWT signing key available")

        # Token payload
        payload = {
            "sub": str(service_account_id),
            "role": role,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(minutes=30),
            "key_version": current_key.version  # Include key version in token
        }

        # Sign with current private key
        token = jwt.encode(
            payload,
            current_key.private_key,
            algorithm=current_key.algorithm
        )

        return token

    def validate_token(self, token: str) -> dict:
        """Validate JWT token using all active keys (for grace period)."""
        active_keys = JWTKey.get_active_keys(self.db)

        if not active_keys:
            raise HTTPException(status_code=401, detail="No active JWT keys")

        # Try to validate with each active key
        for key in active_keys:
            try:
                payload = jwt.decode(
                    token,
                    key.public_key,
                    algorithms=[key.algorithm]
                )

                # Token validated successfully
                logger.debug(f"Token validated with key version: {key.version}")
                return payload

            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token expired")

            except jwt.InvalidTokenError:
                # Try next key
                continue

        # Token invalid with all active keys
        raise HTTPException(status_code=401, detail="Invalid token")
```

**Step 7: Add Prometheus Metrics**

**File**: `admin-module/app/core/metrics.py` (UPDATE)
```python
from prometheus_client import Counter, Gauge

# JWT key rotation metrics
jwt_rotation_total = Counter(
    'jwt_key_rotation_total',
    'Total number of JWT key rotations',
    ['status']  # success | failure
)

jwt_rotation_duration_seconds = Histogram(
    'jwt_key_rotation_duration_seconds',
    'JWT key rotation duration in seconds'
)

jwt_active_keys_count = Gauge(
    'jwt_active_keys_count',
    'Number of currently active JWT keys'
)

# Update metrics in rotation service
# ... (add to JWTKeyRotationService.rotate_keys())
```

**Step 8: Testing**

```bash
# Test manual key rotation
docker exec -it artstore_admin python -c "
from app.core.database import SessionLocal
from app.core.redis import get_redis_client
from app.services.jwt_rotation import JWTKeyRotationService

db = SessionLocal()
redis_client = get_redis_client()
service = JWTKeyRotationService(db, redis_client)

# Force rotation
new_key = service.rotate_keys()
print(f'New key created: {new_key.version}')
print(f'Expires at: {new_key.expires_at}')

# Check active keys
active_keys = service.get_active_keys()
print(f'Active keys count: {len(active_keys)}')
"

# Test token generation with new key
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"admin-service","client_secret":"SECRET"}'

# Verify scheduler running
docker logs artstore_admin | grep "Background scheduler started"
```

**Dependencies**:
```bash
# Add to admin-module/requirements.txt
APScheduler==3.10.4
cryptography==42.0.0  # Already present
```

**Files Created/Modified**:
- `admin-module/alembic/versions/XXXXXX_add_jwt_key_versioning.py` (NEW, 50 lines)
- `admin-module/app/models/jwt_key.py` (NEW, 120 lines)
- `admin-module/app/services/jwt_rotation.py` (NEW, 150 lines)
- `admin-module/app/core/scheduler.py` (NEW, 80 lines)
- `admin-module/app/main.py` (MODIFIED, +10 lines)
- `admin-module/app/services/auth_service.py` (MODIFIED, +50 lines)
- `admin-module/app/core/metrics.py` (MODIFIED, +15 lines)
- `admin-module/requirements.txt` (MODIFIED, +1 line)

**Validation**:
- [ ] Database migration successful
- [ ] JWT keys table created
- [ ] Background scheduler starts on app startup
- [ ] Automatic rotation every 24 hours
- [ ] Grace period supports old + new keys simultaneously
- [ ] Prometheus metrics tracking rotation events
- [ ] Manual rotation testing successful

---

### 2.2 Comprehensive Audit Logging

**Objective**: Structured audit logs для всех security events с tamper-proof signatures.

#### Implementation Steps

**Step 1: Create Audit Log Database Schema**

**File**: `admin-module/alembic/versions/YYYYYY_add_audit_logging.py` (NEW)
```python
"""Add audit logging table

Revision ID: YYYYYY
Revises: XXXXXX
Create Date: 2025-11-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'YYYYYY'
down_revision = 'XXXXXX'

def upgrade():
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('event_type', sa.String(50), nullable=False, index=True),
        sa.Column('event_category', sa.String(30), nullable=False, index=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), nullable=True, index=True),
        sa.Column('service_account_id', sa.Integer(), nullable=True, index=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.String(100), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('signature', sa.String(64), nullable=False),
        schema=None
    )

    # Indexes for efficient queries
    op.create_index('idx_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('idx_audit_logs_event_type', 'audit_logs', ['event_type'])
    op.create_index('idx_audit_logs_status', 'audit_logs', ['status'])

def downgrade():
    op.drop_index('idx_audit_logs_status', table_name='audit_logs')
    op.drop_index('idx_audit_logs_event_type', table_name='audit_logs')
    op.drop_index('idx_audit_logs_timestamp', table_name='audit_logs')
    op.drop_table('audit_logs')
```

**Step 2: Create Audit Log Model**

**File**: `admin-module/app/models/audit_log.py` (NEW)
```python
"""Audit logging model for security events."""
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.settings import get_settings
from app.db.base_class import Base

settings = get_settings()


class AuditLog(Base):
    """Audit log entry with tamper-proof signature."""

    __tablename__ = "audit_logs"

    # Event Categories
    CATEGORY_AUTH = "authentication"
    CATEGORY_AUTHZ = "authorization"
    CATEGORY_DATA = "data_operation"
    CATEGORY_ADMIN = "administration"
    CATEGORY_SECURITY = "security"

    # Event Types
    EVENT_AUTH_SUCCESS = "auth_success"
    EVENT_AUTH_FAILURE = "auth_failure"
    EVENT_AUTHZ_DENIED = "authorization_denied"
    EVENT_FILE_UPLOAD = "file_upload"
    EVENT_FILE_DELETE = "file_delete"
    EVENT_FILE_TRANSFER = "file_transfer"
    EVENT_SERVICE_ACCOUNT_CREATED = "service_account_created"
    EVENT_SERVICE_ACCOUNT_DELETED = "service_account_deleted"
    EVENT_SECRET_ROTATED = "secret_rotated"
    EVENT_KEY_ROTATED = "key_rotated"

    # Status Values
    STATUS_SUCCESS = "success"
    STATUS_FAILURE = "failure"
    STATUS_DENIED = "denied"

    id = Column(BigInteger, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_category = Column(String(30), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    service_account_id = Column(Integer, nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    action = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    details = Column(JSONB, nullable=True)
    signature = Column(String(64), nullable=False)

    def compute_signature(self) -> str:
        """
        Compute HMAC-SHA256 signature for tamper detection.

        Returns:
            str: Hexadecimal signature
        """
        # Canonical representation for signing
        data_to_sign = {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": self.user_id,
            "service_account_id": self.service_account_id,
            "action": self.action,
            "status": self.status,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
        }

        # Sort keys for deterministic serialization
        canonical_json = json.dumps(data_to_sign, sort_keys=True)

        # HMAC-SHA256 signature
        secret_key = settings.audit_log_secret_key.encode('utf-8')
        signature = hmac.new(
            secret_key,
            canonical_json.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    @classmethod
    def create_log(
        cls,
        session,
        event_type: str,
        event_category: str,
        action: str,
        status: str,
        user_id: Optional[int] = None,
        service_account_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> "AuditLog":
        """
        Create audit log entry with automatic signature.

        Args:
            session: Database session
            event_type: Type of event (e.g., "auth_success")
            event_category: Category (auth, authz, data, admin, security)
            action: Action performed (e.g., "login", "file_upload")
            status: Status (success, failure, denied)
            user_id: User ID if applicable
            service_account_id: Service Account ID if applicable
            ip_address: Client IP address
            user_agent: Client User-Agent header
            resource_type: Type of resource (e.g., "file", "service_account")
            resource_id: Resource identifier
            details: Additional structured data (JSONB)

        Returns:
            AuditLog: Created audit log entry
        """
        audit_log = cls(
            event_type=event_type,
            event_category=event_category,
            action=action,
            status=status,
            user_id=user_id,
            service_account_id=service_account_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )

        # Set timestamp explicitly for signature computation
        audit_log.timestamp = datetime.utcnow()

        # Compute and set signature
        audit_log.signature = audit_log.compute_signature()

        session.add(audit_log)
        session.commit()
        session.refresh(audit_log)

        return audit_log

    def verify_signature(self) -> bool:
        """
        Verify audit log signature for tamper detection.

        Returns:
            bool: True if signature is valid, False if tampered
        """
        expected_signature = self.compute_signature()
        return hmac.compare_digest(self.signature, expected_signature)
```

**Step 3: Create Audit Logging Service**

**File**: `admin-module/app/services/audit_service.py` (NEW)
```python
"""Audit logging service for security events."""
import logging
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Service for creating audit logs."""

    def __init__(self, db: Session):
        self.db = db

    def log_authentication_attempt(
        self,
        request: Request,
        client_id: str,
        success: bool,
        reason: Optional[str] = None,
    ):
        """Log authentication attempt (success or failure)."""
        AuditLog.create_log(
            session=self.db,
            event_type=AuditLog.EVENT_AUTH_SUCCESS if success else AuditLog.EVENT_AUTH_FAILURE,
            event_category=AuditLog.CATEGORY_AUTH,
            action="authenticate",
            status=AuditLog.STATUS_SUCCESS if success else AuditLog.STATUS_FAILURE,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={
                "client_id": client_id,
                "reason": reason,
                "endpoint": str(request.url),
            }
        )

        logger.info(f"Audit: Authentication {'success' if success else 'failure'} for client_id={client_id}")

    def log_authorization_denied(
        self,
        request: Request,
        user_id: Optional[int],
        service_account_id: Optional[int],
        resource_type: str,
        resource_id: str,
        action: str,
        reason: str,
    ):
        """Log authorization denial."""
        AuditLog.create_log(
            session=self.db,
            event_type=AuditLog.EVENT_AUTHZ_DENIED,
            event_category=AuditLog.CATEGORY_AUTHZ,
            action=action,
            status=AuditLog.STATUS_DENIED,
            user_id=user_id,
            service_account_id=service_account_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            resource_type=resource_type,
            resource_id=resource_id,
            details={
                "reason": reason,
                "endpoint": str(request.url),
            }
        )

        logger.warning(f"Audit: Authorization denied for action={action} on {resource_type}/{resource_id}")

    def log_file_operation(
        self,
        request: Request,
        service_account_id: int,
        operation: str,  # upload, delete, transfer
        file_id: str,
        file_name: str,
        file_size: Optional[int] = None,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log file operations (upload, delete, transfer)."""
        event_type_map = {
            "upload": AuditLog.EVENT_FILE_UPLOAD,
            "delete": AuditLog.EVENT_FILE_DELETE,
            "transfer": AuditLog.EVENT_FILE_TRANSFER,
        }

        event_details = {
            "file_name": file_name,
            "file_size": file_size,
            **(details or {})
        }

        AuditLog.create_log(
            session=self.db,
            event_type=event_type_map.get(operation, "file_operation"),
            event_category=AuditLog.CATEGORY_DATA,
            action=operation,
            status=AuditLog.STATUS_SUCCESS if success else AuditLog.STATUS_FAILURE,
            service_account_id=service_account_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            resource_type="file",
            resource_id=file_id,
            details=event_details,
        )

        logger.info(f"Audit: File {operation} for file_id={file_id}, file_name={file_name}")

    def log_key_rotation(
        self,
        key_version: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log JWT key rotation event."""
        AuditLog.create_log(
            session=self.db,
            event_type=AuditLog.EVENT_KEY_ROTATED,
            event_category=AuditLog.CATEGORY_SECURITY,
            action="rotate_jwt_key",
            status=AuditLog.STATUS_SUCCESS if success else AuditLog.STATUS_FAILURE,
            resource_type="jwt_key",
            resource_id=key_version,
            details=details,
        )

        logger.info(f"Audit: JWT key rotation, version={key_version}, success={success}")
```

**Step 4: Create Audit Middleware**

**File**: `admin-module/app/middleware/audit_middleware.py` (NEW)
```python
"""Middleware for automatic audit logging."""
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import SessionLocal
from app.services.audit_service import AuditService


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware для автоматического audit logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log security-relevant events."""
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Log authentication failures (401)
        if response.status_code == 401 and request.url.path.startswith("/api/v1/auth"):
            db = SessionLocal()
            try:
                audit_service = AuditService(db)
                audit_service.log_authentication_attempt(
                    request=request,
                    client_id=request.headers.get("X-Client-ID", "unknown"),
                    success=False,
                    reason=f"HTTP {response.status_code}"
                )
            finally:
                db.close()

        # Log authorization failures (403)
        if response.status_code == 403:
            db = SessionLocal()
            try:
                audit_service = AuditService(db)
                audit_service.log_authorization_denied(
                    request=request,
                    user_id=getattr(request.state, "user_id", None),
                    service_account_id=getattr(request.state, "service_account_id", None),
                    resource_type="api",
                    resource_id=request.url.path,
                    action=request.method,
                    reason=f"HTTP {response.status_code}"
                )
            finally:
                db.close()

        return response
```

**Step 5: Update Settings for Audit Secret**

**File**: `admin-module/app/core/settings.py` (UPDATE)
```python
class Settings(BaseModel):
    # ... existing settings ...

    # Audit Logging
    audit_log_secret_key: str = Field(
        default="CHANGE_THIS_TO_STRONG_RANDOM_KEY_32_CHARS",
        description="Secret key for HMAC signing of audit logs"
    )

    audit_log_retention_days: int = Field(
        default=2555,  # ~7 years
        description="Audit log retention period in days"
    )
```

**File**: `.env.example` (UPDATE)
```bash
# Audit Logging
AUDIT_LOG_SECRET_KEY=REPLACE_WITH_STRONG_RANDOM_KEY_32_CHARS
AUDIT_LOG_RETENTION_DAYS=2555  # ~7 years
```

**Step 6: Add Prometheus Metrics**

**File**: `admin-module/app/core/metrics.py` (UPDATE)
```python
# Audit logging metrics
audit_log_total = Counter(
    'audit_log_total',
    'Total number of audit log entries',
    ['event_category', 'event_type', 'status']
)

audit_log_verification_failures = Counter(
    'audit_log_verification_failures_total',
    'Number of audit log signature verification failures'
)
```

**Step 7: Testing**

```bash
# Test authentication audit logging
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"invalid","client_secret":"wrong"}' \
  -v

# Verify audit log created
docker exec -it artstore_postgres psql -U artstore -d artstore \
  -c "SELECT event_type, status, details FROM audit_logs ORDER BY timestamp DESC LIMIT 1;"

# Test signature verification
docker exec -it artstore_admin python -c "
from app.core.database import SessionLocal
from app.models.audit_log import AuditLog

db = SessionLocal()
log = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
print(f'Event: {log.event_type}')
print(f'Signature valid: {log.verify_signature()}')
"

# Test file upload audit logging
curl -X POST http://localhost:8020/api/v1/files/upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@test.txt"

# Check audit logs for file upload
docker exec -it artstore_postgres psql -U artstore -d artstore \
  -c "SELECT event_type, action, resource_id, details FROM audit_logs WHERE event_category='data_operation' ORDER BY timestamp DESC LIMIT 5;"
```

**Dependencies**:
```bash
# No additional dependencies needed (stdlib only)
```

**Files Created/Modified**:
- `admin-module/alembic/versions/YYYYYY_add_audit_logging.py` (NEW, 50 lines)
- `admin-module/app/models/audit_log.py` (NEW, 200 lines)
- `admin-module/app/services/audit_service.py` (NEW, 150 lines)
- `admin-module/app/middleware/audit_middleware.py` (NEW, 60 lines)
- `admin-module/app/core/settings.py` (MODIFIED, +10 lines)
- `.env.example` (MODIFIED, +3 lines)
- `admin-module/app/core/metrics.py` (MODIFIED, +10 lines)

**Apply to Other Modules**:
- Replicate audit logging to `ingester-module` (file operations)
- Replicate to `query-module` (search/download operations)
- Replicate to `storage-element` (file storage operations)

**Validation**:
- [ ] Audit logs table created
- [ ] All authentication attempts logged
- [ ] All authorization failures logged
- [ ] File operations (upload, delete, transfer) logged
- [ ] Key rotation events logged
- [ ] HMAC signatures computed correctly
- [ ] Signature verification working
- [ ] 7-year retention policy configured
- [ ] Prometheus metrics tracking audit events

---

**Phase 2 Deliverables**:
- ✅ JWT key rotation automated (every 24 hours)
- ✅ Comprehensive audit logging operational
- ✅ Tamper-proof log signatures (HMAC-SHA256)
- ✅ 7-year audit log retention
- ✅ Prometheus metrics for security events
- **Files Modified**: ~20
- **Files Created**: ~10
- **Lines Added**: ~1,000
- **Security Score**: 6.5/10 → 7.5/10 (+15%)

---

## Phase 3: Secrets Management (Week 15.3)

**Duration**: 2-3 дня
**Priority**: P1
**Complexity**: MEDIUM

### 3.1 Docker Secrets Integration

**Objective**: Migrate all sensitive credentials to Docker Secrets для production-grade secrets management.

#### Implementation Steps

**Step 1: Create Docker Secrets**

**File**: `scripts/create_docker_secrets.sh` (NEW)
```bash
#!/bin/bash
# create_docker_secrets.sh - Create Docker Secrets for all services

set -e

echo "Creating Docker Secrets for ArtStore..."

# Read passwords from .env or prompt
if [ -f .env ]; then
    source .env
else
    echo "Error: .env file not found. Run ./scripts/generate_secrets.sh first."
    exit 1
fi

# PostgreSQL credentials
echo "${POSTGRES_PASSWORD}" | docker secret create postgres_password - 2>/dev/null || echo "Secret postgres_password already exists"

# Redis password
echo "${REDIS_PASSWORD}" | docker secret create redis_password - 2>/dev/null || echo "Secret redis_password already exists"

# JWT private key (read from file)
if [ -f keys/jwt_private_key.pem ]; then
    docker secret create jwt_private_key keys/jwt_private_key.pem 2>/dev/null || echo "Secret jwt_private_key already exists"
else
    echo "Warning: keys/jwt_private_key.pem not found"
fi

# Audit log secret key
echo "${AUDIT_LOG_SECRET_KEY}" | docker secret create audit_log_secret - 2>/dev/null || echo "Secret audit_log_secret already exists"

# List created secrets
echo ""
echo "✅ Docker Secrets created:"
docker secret ls

echo ""
echo "To remove all secrets: docker secret rm postgres_password redis_password jwt_private_key audit_log_secret"
```

**Step 2: Update docker-compose.yml for Secrets**

**File**: `docker-compose.yml` (MODIFY)
```yaml
version: "3.8"

services:
  postgres:
    image: postgres:15
    container_name: artstore_postgres
    environment:
      - POSTGRES_USER=artstore
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password  # Changed from POSTGRES_PASSWORD
      - POSTGRES_DB=artstore
    secrets:
      - postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U artstore"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7
    container_name: artstore_redis
    command: >
      sh -c 'redis-server --requirepass "$$(cat /run/secrets/redis_password)"'
    secrets:
      - redis_password
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "$$(cat /run/secrets/redis_password)", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  admin-module:
    build:
      context: ./admin-module
      dockerfile: Dockerfile
    container_name: artstore_admin
    environment:
      - DATABASE_URL=postgresql://artstore@postgres:5432/artstore
      - REDIS_URL=redis://:@redis:6379/0
      - JWT_PRIVATE_KEY_FILE=/run/secrets/jwt_private_key  # New
      - AUDIT_LOG_SECRET_FILE=/run/secrets/audit_log_secret  # New
    secrets:
      - jwt_private_key
      - audit_log_secret
      - postgres_password
      - redis_password
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"

# Define secrets
secrets:
  postgres_password:
    external: true
  redis_password:
    external: true
  jwt_private_key:
    external: true
  audit_log_secret:
    external: true

volumes:
  postgres_data:
```

**Step 3: Update Application Settings to Read from Secrets**

**File**: `admin-module/app/core/settings.py` (MODIFY)
```python
import os
from pathlib import Path
from typing import Optional

class Settings(BaseModel):
    # ... existing settings ...

    @staticmethod
    def read_secret_file(file_path: str) -> str:
        """Read secret from Docker Secrets file."""
        if not file_path:
            raise ValueError("Secret file path not provided")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Secret file not found: {file_path}")

        return path.read_text().strip()

    @classmethod
    def get_postgres_password(cls) -> str:
        """Get PostgreSQL password from Docker Secret or environment."""
        secret_file = os.getenv("POSTGRES_PASSWORD_FILE")
        if secret_file:
            return cls.read_secret_file(secret_file)

        # Fallback to environment variable (development mode)
        password = os.getenv("POSTGRES_PASSWORD")
        if not password:
            raise ValueError("PostgreSQL password not configured")

        return password

    @classmethod
    def get_redis_password(cls) -> str:
        """Get Redis password from Docker Secret or environment."""
        secret_file = os.getenv("REDIS_PASSWORD_FILE")
        if secret_file:
            return cls.read_secret_file(secret_file)

        # Fallback to environment variable (development mode)
        password = os.getenv("REDIS_PASSWORD", "")
        return password

    @classmethod
    def get_jwt_private_key(cls) -> str:
        """Get JWT private key from Docker Secret or file."""
        secret_file = os.getenv("JWT_PRIVATE_KEY_FILE")
        if secret_file:
            return cls.read_secret_file(secret_file)

        # Fallback to local file (development mode)
        key_path = os.getenv("JWT_PRIVATE_KEY_PATH", "keys/jwt_private_key.pem")
        return Path(key_path).read_text()

    @classmethod
    def get_audit_log_secret(cls) -> str:
        """Get audit log secret from Docker Secret or environment."""
        secret_file = os.getenv("AUDIT_LOG_SECRET_FILE")
        if secret_file:
            return cls.read_secret_file(secret_file)

        # Fallback to environment variable (development mode)
        secret = os.getenv("AUDIT_LOG_SECRET_KEY")
        if not secret:
            raise ValueError("Audit log secret not configured")

        return secret

    # Update settings to use secret readers
    database_url: str = Field(
        default_factory=lambda: f"postgresql://artstore:{Settings.get_postgres_password()}@localhost:5432/artstore"
    )

    redis_url: str = Field(
        default_factory=lambda: f"redis://:{Settings.get_redis_password()}@localhost:6379/0"
    )

    jwt_private_key: str = Field(
        default_factory=Settings.get_jwt_private_key
    )

    audit_log_secret_key: str = Field(
        default_factory=Settings.get_audit_log_secret
    )
```

**Step 4: Development Mode Fallback**

**File**: `docker-compose.dev.yml` (NEW)
```yaml
# Development mode - uses .env file instead of Docker Secrets
version: "3.8"

services:
  postgres:
    image: postgres:15
    container_name: artstore_postgres_dev
    environment:
      - POSTGRES_USER=artstore
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}  # From .env
      - POSTGRES_DB=artstore
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    container_name: artstore_redis_dev
    command: redis-server --requirepass ${REDIS_PASSWORD}  # From .env
    ports:
      - "6379:6379"

  admin-module:
    build:
      context: ./admin-module
      dockerfile: Dockerfile
    container_name: artstore_admin_dev
    environment:
      - DATABASE_URL=postgresql://artstore:${POSTGRES_PASSWORD}@postgres:5432/artstore
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - AUDIT_LOG_SECRET_KEY=${AUDIT_LOG_SECRET_KEY}
      - JWT_PRIVATE_KEY_PATH=./keys/jwt_private_key.pem
      - ENVIRONMENT=development
    volumes:
      - ./admin-module:/app  # Hot reload
      - ./keys:/app/keys
    ports:
      - "8000:8000"
```

**Step 5: Documentation**

**File**: `docs/SECRETS_MANAGEMENT.md` (NEW)
```markdown
# Secrets Management Guide

## Production Mode (Docker Secrets)

### Initial Setup
```bash
# 1. Generate secrets
./scripts/generate_secrets.sh > .env

# 2. Create Docker Secrets
./scripts/create_docker_secrets.sh

# 3. Start services
docker-compose up -d
```

### Secret Rotation
```bash
# 1. Generate new password
NEW_PASSWORD=$(openssl rand -base64 24)

# 2. Update PostgreSQL password
echo "${NEW_PASSWORD}" | docker secret create postgres_password_new -

# 3. Update docker-compose.yml to use new secret
# Change: secrets: [postgres_password_new]

# 4. Restart services
docker-compose up -d --force-recreate postgres

# 5. Remove old secret
docker secret rm postgres_password
```

## Development Mode (.env files)

```bash
# Use development docker-compose
docker-compose -f docker-compose.dev.yml up -d
```

## Security Best Practices

1. **Never commit .env files** to version control
2. **Rotate secrets regularly**: PostgreSQL/Redis every 90 days
3. **Use different secrets** for dev/staging/production
4. **Backup .env files securely**: Encrypted cloud storage or password manager
5. **Restrict secret access**: Only authorized personnel
6. **Monitor secret usage**: Audit logs track all secret accesses
7. **Automate rotation**: Use scripts for consistent process

## Troubleshooting

### Secret not found error
```bash
# Check if secret exists
docker secret ls

# Recreate secret
echo "NEW_PASSWORD" | docker secret create secret_name -
```

### Permission denied reading secret
```bash
# Secrets must be created in Docker Swarm mode
docker swarm init
./scripts/create_docker_secrets.sh
```
```

**Step 6: Testing**

```bash
# Test production mode (Docker Secrets)
./scripts/generate_secrets.sh > .env
docker swarm init  # Required for Docker Secrets
./scripts/create_docker_secrets.sh
docker stack deploy -c docker-compose.yml artstore

# Verify secrets accessible
docker exec artstore_admin cat /run/secrets/postgres_password
docker exec artstore_admin cat /run/secrets/jwt_private_key

# Test development mode (.env files)
docker-compose -f docker-compose.dev.yml up -d
docker logs artstore_admin_dev | grep "Application startup"
```

**Files Created/Modified**:
- `scripts/create_docker_secrets.sh` (NEW, 50 lines)
- `docker-compose.yml` (MODIFIED, +30 lines - secrets config)
- `docker-compose.dev.yml` (NEW, 80 lines - development mode)
- `admin-module/app/core/settings.py` (MODIFIED, +80 lines - secret readers)
- `docs/SECRETS_MANAGEMENT.md` (NEW, 150 lines)
- Apply similar changes to other 3 modules

**Validation**:
- [ ] Docker Secrets created successfully
- [ ] Services start with Docker Secrets
- [ ] No plain-text secrets in docker-compose.yml
- [ ] Development mode works with .env fallback
- [ ] Secret rotation procedures documented
- [ ] All modules using Docker Secrets

---

**Phase 3 Deliverables**:
- ✅ Docker Secrets managing PostgreSQL, Redis, JWT keys, Audit secrets
- ✅ Production docker-compose.yml with secrets
- ✅ Development mode with .env fallback
- ✅ Secret rotation procedures documented
- ✅ Zero plain-text secrets in configuration
- **Files Modified**: ~15
- **Files Created**: ~5
- **Lines Added**: ~500
- **Security Score**: 7.5/10 → 8/10 (+7%)

---

## Sprint 15 Summary

### Overall Deliverables

**Phase 1: Quick Security Wins** (1-2 дня):
- ✅ CORS Whitelist Configuration (4 modules)
- ✅ Strong Random Passwords (all services)

**Phase 2: Authentication & Logging** (3-5 дней):
- ✅ JWT Key Rotation Automation (24-hour cycle)
- ✅ Comprehensive Audit Logging (all security events)

**Phase 3: Secrets Management** (2-3 дня):
- ✅ Docker Secrets Integration (production)
- ✅ Development mode fallback (.env)

### Metrics

| Metric | Value |
|--------|-------|
| **Security Score** | 6/10 → 8/10 (+33%) |
| **MUST HAVE Items Completed** | 5/7 (71%) |
| **Critical Gaps Closed** | CORS, Passwords, JWT Rotation, Audit Logging, Secrets |
| **Production Blockers Remaining** | 2 (TLS 1.3, mTLS - Sprint 16) |
| **Files Created** | ~18 |
| **Files Modified** | ~45 |
| **Lines Added** | ~1,700 |
| **New Components** | 3 (JWT Rotation Scheduler, Audit Service, Secrets Reader) |
| **Documentation** | 4 new guides (Security Setup, Secrets Management, Audit Logging, Key Rotation) |

### Success Criteria

- ✅ CORS configured with explicit whitelists (no wildcards)
- ✅ All default passwords replaced with strong random values (32+ chars)
- ✅ JWT keys rotate automatically every 24 hours with graceful transition
- ✅ Comprehensive audit logging operational (authentication, authorization, file ops, key rotation)
- ✅ Docker Secrets managing all sensitive credentials in production
- ✅ Security score improved to 8/10
- ✅ Zero plain-text secrets in docker-compose.yml
- ✅ Prometheus metrics tracking all security events

### Next Steps (Sprint 16)

**TLS 1.3 + mTLS Implementation** (2 недели):
- Certificate infrastructure setup (self-signed for development, CA for production)
- TLS 1.3 configuration for all services
- mTLS (mutual TLS) for inter-service communication
- Certificate rotation automation
- **Expected**: Security score 8/10 → 10/10

---

**Sprint 15 Expected Outcome**: Critical security hardening complete, production deployment blockers reduced from 6 to 2 (only TLS/mTLS remaining).
