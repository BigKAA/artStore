"""
Custom SQLAlchemy types для cross-database compatibility.

Provides fallback types для тестирования с SQLite.
"""

from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PostgreSQL_UUID
import uuid as uuid_lib


class UUID(TypeDecorator):
    """
    Platform-independent UUID type.

    Uses PostgreSQL UUID type when available, falls back to CHAR(36) for SQLite.
    Stores UUID as string in SQLite для compatibility.

    Usage:
        from app.db.types import UUID

        class MyModel(Base):
            id = Column(UUID(as_uuid=True), primary_key=True)
    """

    impl = CHAR
    cache_ok = True

    def __init__(self, as_uuid=True):
        """
        Initialize UUID type.

        Args:
            as_uuid: If True, returns uuid.UUID objects; if False, returns strings
        """
        self.as_uuid = as_uuid
        super().__init__()

    def load_dialect_impl(self, dialect):
        """
        Load appropriate implementation for database dialect.

        Args:
            dialect: SQLAlchemy dialect

        Returns:
            Appropriate type implementation
        """
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PostgreSQL_UUID(as_uuid=self.as_uuid))
        else:
            # SQLite fallback: store as CHAR(36)
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        """
        Process value before binding to database.

        Args:
            value: UUID value (uuid.UUID, string, or None)
            dialect: Database dialect

        Returns:
            Processed value for database
        """
        if value is None:
            return None

        if dialect.name == 'postgresql':
            # PostgreSQL handles UUID natively
            if isinstance(value, uuid_lib.UUID):
                return value
            return uuid_lib.UUID(value) if self.as_uuid else str(value)
        else:
            # SQLite: store as string
            if isinstance(value, uuid_lib.UUID):
                return str(value)
            return str(uuid_lib.UUID(value))  # Validate UUID format

    def process_result_value(self, value, dialect):
        """
        Process value when retrieving from database.

        Args:
            value: Value from database
            dialect: Database dialect

        Returns:
            uuid.UUID object or string
        """
        if value is None:
            return None

        if dialect.name == 'postgresql':
            # PostgreSQL returns UUID or string depending on as_uuid
            if self.as_uuid and isinstance(value, str):
                return uuid_lib.UUID(value)
            return value
        else:
            # SQLite returns string, convert if needed
            if self.as_uuid:
                return uuid_lib.UUID(value)
            return value
