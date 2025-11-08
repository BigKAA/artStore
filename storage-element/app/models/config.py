"""
Configuration storage model для Storage Element.

PostgreSQL table для runtime configuration и settings.
"""

from sqlalchemy import Column, String, TIMESTAMP, Text, Index
from sqlalchemy.sql import func
from datetime import datetime, timezone

from app.db.base import Base
from app.core.config import get_config


class Config(Base):
    """
    Runtime configuration table.

    Хранит конфигурацию storage element которая может изменяться в runtime:
    - Storage mode (edit, rw, ro, ar)
    - Current master node (для HA clusters)
    - Service Discovery status
    - Runtime settings
    """

    # Динамическое имя таблицы из конфигурации
    config = get_config()
    __tablename__ = f"{config.database.table_prefix}_config"

    # Primary Key
    key = Column(
        String(255),
        primary_key=True,
        comment="Configuration key"
    )

    # Value
    value = Column(
        Text,
        nullable=False,
        comment="Configuration value (can be JSON string)"
    )

    # Description
    description = Column(
        Text,
        comment="Human-readable description of this setting"
    )

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Setting creation time"
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Last update time"
    )

    # Indexes
    __table_args__ = (
        Index('ix_config_updated_at', 'updated_at'),
    )

    def __repr__(self):
        return f"<Config(key='{self.key}', value='{self.value[:50]}...')>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Common config keys константы
class ConfigKeys:
    """Common configuration keys."""

    STORAGE_MODE = "storage_mode"  # edit | rw | ro | ar
    MASTER_NODE_ID = "master_node_id"  # For HA clusters
    SERVICE_DISCOVERY_STATUS = "service_discovery_status"  # enabled | disabled
    LAST_RECONCILIATION = "last_reconciliation"  # Timestamp of last attr.json reconciliation
    TOTAL_FILES = "total_files"  # Cached file count
    TOTAL_SIZE_BYTES = "total_size_bytes"  # Cached total storage size
    AVAILABLE_SPACE_BYTES = "available_space_bytes"  # Available disk space
