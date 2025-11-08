"""
Write-Ahead Log (WAL) model для Storage Element.

PostgreSQL table для транзакционного журнала операций.
"""

from sqlalchemy import (
    Column, BigInteger, String, TIMESTAMP, CheckConstraint, Index, JSON, Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from datetime import datetime, timezone
import uuid as uuid_lib

from app.db.base import Base
from app.core.config import get_config


class WAL(Base):
    """
    Write-Ahead Log table для транзакционности операций.

    Обеспечивает:
    - Атомарность операций
    - Восстановление после сбоев
    - Audit trail всех операций
    - Поддержка Saga Pattern
    """

    # Динамическое имя таблицы из конфигурации
    config = get_config()
    __tablename__ = f"{config.database.table_prefix}_wal"

    # Primary Key (Integer для SQLite compatibility, в PostgreSQL будет BigInteger)
    wal_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="WAL entry sequential ID"
    )

    # Transaction Info
    transaction_id = Column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid_lib.uuid4,
        comment="Unique transaction identifier"
    )

    saga_id = Column(
        String(255),
        comment="Saga ID для распределенных транзакций"
    )

    # Operation Details
    operation_type = Column(
        String(50),
        nullable=False,
        comment="Operation type: upload, delete, update_metadata, mode_change"
    )

    operation_status = Column(
        String(50),
        nullable=False,
        default='pending',
        comment="Status: pending, in_progress, committed, rolled_back, failed"
    )

    # Target Resource
    file_id = Column(
        UUID(as_uuid=True),
        comment="File ID if operation is file-specific"
    )

    # Operation Payload (JSON для совместимости с SQLite, в PostgreSQL будет JSONB)
    payload = Column(
        JSON,
        nullable=False,
        comment="Operation data (JSON)"
    )

    # Compensation Data для rollback
    compensation_data = Column(
        JSON,
        comment="Data for compensating transaction (rollback)"
    )

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Transaction creation time"
    )

    committed_at = Column(
        TIMESTAMP(timezone=True),
        comment="Transaction commit time"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('upload', 'delete', 'update_metadata', 'mode_change')",
            name='ck_operation_type'
        ),
        CheckConstraint(
            "operation_status IN ('pending', 'in_progress', 'committed', 'rolled_back', 'failed')",
            name='ck_operation_status'
        ),

        # Indexes
        Index('ix_wal_transaction_id', 'transaction_id'),
        Index('ix_wal_status', 'operation_status'),
        Index('ix_wal_created_at', 'created_at', postgresql_using='btree'),
        Index('ix_wal_saga_id', 'saga_id'),

        # Partial index для незавершенных транзакций
        Index(
            'ix_wal_pending',
            'operation_status',
            postgresql_where="operation_status IN ('pending', 'in_progress')"
        ),

        # GIN index для JSONB payload search (только PostgreSQL, добавится через migration)
        # Index('ix_wal_payload', 'payload', postgresql_using='gin'),
    )

    def __repr__(self):
        return (
            f"<WAL(wal_id={self.wal_id}, "
            f"transaction_id={self.transaction_id}, "
            f"operation_type='{self.operation_type}', "
            f"status='{self.operation_status}')>"
        )

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "wal_id": self.wal_id,
            "transaction_id": str(self.transaction_id),
            "saga_id": self.saga_id,
            "operation_type": self.operation_type,
            "operation_status": self.operation_status,
            "file_id": str(self.file_id) if self.file_id else None,
            "payload": self.payload,
            "compensation_data": self.compensation_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "committed_at": self.committed_at.isoformat() if self.committed_at else None,
        }
