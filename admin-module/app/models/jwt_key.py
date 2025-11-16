"""
JWT Key Model для автоматической ротации ключей.

Поддерживает:
- Автоматическая генерация RSA key pairs (2048-bit)
- Key versioning через UUID
- Graceful transition period (25h = 24h + 1h overlap)
- Multi-version validation support
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, select
from sqlalchemy.orm import Session

from app.models.base import Base


class JWTKey(Base):
    """
    JWT Key version для rotation support.

    Attributes:
        id: Primary key (автоинкремент)
        version: UUID идентификатор key version
        private_key: RSA private key (PEM format, 2048-bit)
        public_key: RSA public key (PEM format, 2048-bit)
        algorithm: JWT signing algorithm (RS256 only)
        created_at: Key creation timestamp
        expires_at: Key expiration timestamp (created_at + 25h)
        is_active: Active status (false = expired/deactivated)
        rotation_count: Number of rotation cycles
    """

    __tablename__ = "jwt_keys"

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)

    # Version UUID
    version = Column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID version identifier"
    )

    # Cryptographic Keys (PEM format)
    private_key = Column(
        Text,
        nullable=False,
        comment="RSA private key (PEM, 2048-bit)"
    )
    public_key = Column(
        Text,
        nullable=False,
        comment="RSA public key (PEM, 2048-bit)"
    )

    # Algorithm
    algorithm = Column(
        String(10),
        nullable=False,
        default="RS256",
        comment="JWT signing algorithm"
    )

    # Lifecycle Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Key creation timestamp"
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Key expiration timestamp (25h grace period)"
    )

    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Active status flag"
    )

    # Rotation Metadata
    rotation_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Rotation cycle counter"
    )

    @classmethod
    def create_new_key(
        cls,
        session: Session,
        validity_hours: int = 25
    ) -> "JWTKey":
        """
        Создает новую JWT key pair с указанным validity period.

        Args:
            session: Database session
            validity_hours: Key validity в часах (default 25h = 24h + 1h grace)

        Returns:
            JWTKey: New key instance (не сохранен в БД)

        Note:
            Graceful transition period обеспечивается через validity_hours=25:
            - 24 часа normal operation
            - 1 час overlap period для плавного перехода
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        # Generate RSA 2048-bit key pair
        private_key_obj = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Serialize private key to PEM format
        private_pem = private_key_obj.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        # Extract public key and serialize to PEM format
        public_key_obj = private_key_obj.public_key()
        public_pem = public_key_obj.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        # Calculate expiration timestamp
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=validity_hours)

        # Create new JWTKey instance
        new_key = cls(
            version=str(uuid.uuid4()),
            private_key=private_pem,
            public_key=public_pem,
            algorithm="RS256",
            created_at=now,
            expires_at=expires_at,
            is_active=True,
            rotation_count=0
        )

        return new_key

    @classmethod
    def get_active_keys(cls, session: Session) -> List["JWTKey"]:
        """
        Получает все активные JWT keys (is_active=True).

        Args:
            session: Database session

        Returns:
            List[JWTKey]: List of active keys, ordered by expires_at DESC

        Note:
            Во время graceful transition period может быть 2 активных ключа:
            - Старый ключ (в overlap period)
            - Новый ключ (только что created)
        """
        stmt = (
            select(cls)
            .where(cls.is_active == True)  # noqa: E712
            .order_by(cls.expires_at.desc())
        )
        result = session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    def get_latest_active_key(cls, session: Session) -> Optional["JWTKey"]:
        """
        Получает самый новый активный JWT key для signing.

        Args:
            session: Database session

        Returns:
            Optional[JWTKey]: Latest active key или None

        Note:
            Используется для signing новых JWT tokens.
            Всегда возвращает ключ с наибольшим expires_at.
        """
        stmt = (
            select(cls)
            .where(cls.is_active == True)  # noqa: E712
            .order_by(cls.expires_at.desc())
            .limit(1)
        )
        result = session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    def get_key_by_version(
        cls,
        session: Session,
        version: str
    ) -> Optional["JWTKey"]:
        """
        Получает JWT key по version UUID.

        Args:
            session: Database session
            version: UUID version identifier

        Returns:
            Optional[JWTKey]: Key with specified version или None
        """
        stmt = select(cls).where(cls.version == version)
        result = session.execute(stmt)
        return result.scalar_one_or_none()

    def deactivate(self, session: Session) -> None:
        """
        Деактивирует JWT key (устанавливает is_active=False).

        Args:
            session: Database session

        Note:
            Деактивированные ключи больше не используются для validation,
            но остаются в БД для audit purposes.
        """
        self.is_active = False
        session.add(self)

    @classmethod
    def cleanup_expired_keys(cls, session: Session) -> int:
        """
        Деактивирует все expired JWT keys (expires_at < now).

        Args:
            session: Database session

        Returns:
            int: Number of deactivated keys

        Note:
            Вызывается автоматически при каждой ротации.
            Expired keys деактивируются но не удаляются (audit trail).
        """
        now = datetime.now(timezone.utc)

        # Find all expired active keys
        stmt = (
            select(cls)
            .where(cls.is_active == True)  # noqa: E712
            .where(cls.expires_at < now)
        )
        result = session.execute(stmt)
        expired_keys = result.scalars().all()

        # Deactivate them
        count = 0
        for key in expired_keys:
            key.deactivate(session)
            count += 1

        return count

    def __repr__(self) -> str:
        """String representation для debugging."""
        return (
            f"<JWTKey(id={self.id}, version={self.version[:8]}..., "
            f"algorithm={self.algorithm}, is_active={self.is_active}, "
            f"expires_at={self.expires_at})>"
        )
