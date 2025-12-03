"""Add retention policy and lifecycle management tables.

Revision ID: 20251201_0002
Revises: 20251201_0001
Create Date: 2025-12-01 14:00:00.000000

Sprint 15 - Retention Policy & Lifecycle Implementation:
1. Add `files` table - central file registry with retention_policy support
2. Add `file_finalize_transactions` table - Two-Phase Commit transaction log
3. Add `file_cleanup_queue` table - Garbage Collection queue

Retention Policies:
- TEMPORARY: файлы в Edit SE с TTL (автоматическое удаление через GC)
- PERMANENT: файлы в RW SE (долгосрочное хранение)

Lifecycle Flow:
Upload (temporary) → Finalize (Two-Phase Commit) → Cleanup (GC job)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251201_0002'
down_revision = '20251126_0000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create retention policy and lifecycle management tables."""

    # Создаём ENUM типы для retention policy и статусов
    retention_policy_enum = postgresql.ENUM(
        'temporary', 'permanent',
        name='retention_policy_enum',
        create_type=True
    )

    finalize_transaction_status_enum = postgresql.ENUM(
        'copying', 'copied', 'verifying', 'completed', 'failed', 'rolled_back',
        name='finalize_transaction_status_enum',
        create_type=True
    )

    # 1. Создаём таблицу files - центральный реестр файлов
    # Эта таблица используется для tracking файлов между модулями
    op.create_table(
        'files',
        # Основные идентификаторы
        sa.Column(
            'file_id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Уникальный UUID идентификатор файла (primary key)'
        ),

        # Метаданные файла
        sa.Column(
            'original_filename',
            sa.String(500),
            nullable=False,
            comment='Оригинальное имя файла при загрузке'
        ),
        sa.Column(
            'storage_filename',
            sa.String(500),
            nullable=False,
            comment='Имя файла в storage (может отличаться от оригинала)'
        ),
        sa.Column(
            'file_size',
            sa.BigInteger(),
            nullable=False,
            comment='Размер файла в байтах'
        ),
        sa.Column(
            'checksum_sha256',
            sa.String(64),
            nullable=False,
            comment='SHA-256 checksum файла для integrity verification'
        ),
        sa.Column(
            'content_type',
            sa.String(255),
            nullable=True,
            comment='MIME type файла (application/pdf, image/jpeg, etc.)'
        ),
        sa.Column(
            'description',
            sa.String(1000),
            nullable=True,
            comment='Описание файла (опционально)'
        ),

        # Retention Policy
        sa.Column(
            'retention_policy',
            retention_policy_enum,
            nullable=False,
            server_default='permanent',
            comment='Политика хранения: temporary (Edit SE) или permanent (RW SE)'
        ),
        sa.Column(
            'ttl_expires_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата истечения TTL (только для temporary файлов, default 30 дней)'
        ),
        sa.Column(
            'ttl_days',
            sa.Integer(),
            nullable=True,
            comment='Количество дней TTL при создании (для аудита)'
        ),
        sa.Column(
            'finalized_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата финализации (перехода temporary → permanent)'
        ),

        # Storage Location
        sa.Column(
            'storage_element_id',
            sa.String(255),
            nullable=False,
            comment='ID Storage Element где хранится файл'
        ),
        sa.Column(
            'storage_path',
            sa.String(1000),
            nullable=False,
            comment='Полный путь к файлу внутри Storage Element'
        ),

        # Compression
        sa.Column(
            'compressed',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment='Флаг сжатия файла'
        ),
        sa.Column(
            'compression_algorithm',
            sa.String(20),
            nullable=True,
            comment='Алгоритм сжатия: gzip, brotli, none'
        ),
        sa.Column(
            'original_size',
            sa.BigInteger(),
            nullable=True,
            comment='Оригинальный размер до сжатия (если сжат)'
        ),

        # Ownership and audit
        sa.Column(
            'uploaded_by',
            sa.String(100),
            nullable=True,
            comment='Client ID или User ID загрузившего файл'
        ),
        sa.Column(
            'upload_source_ip',
            sa.String(45),
            nullable=True,
            comment='IP адрес с которого загружен файл'
        ),

        # User-defined metadata (JSON) - переименовано из metadata т.к. reserved name в SQLAlchemy
        sa.Column(
            'user_metadata',
            postgresql.JSONB(),
            nullable=True,
            server_default='{}',
            comment='Пользовательские метаданные (JSON)'
        ),

        # Deletion tracking
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата мягкого удаления (soft delete)'
        ),
        sa.Column(
            'deletion_reason',
            sa.String(255),
            nullable=True,
            comment='Причина удаления: ttl_expired, gc_cleanup, manual, finalized'
        ),

        # Timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment='Дата создания записи'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment='Дата последнего обновления записи'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('file_id', name=op.f('pk_files')),
    )

    # Indexes для files таблицы
    op.create_index(
        'idx_files_retention_policy',
        'files',
        ['retention_policy'],
        unique=False
    )
    op.create_index(
        'idx_files_storage_element',
        'files',
        ['storage_element_id'],
        unique=False
    )
    op.create_index(
        'idx_files_checksum',
        'files',
        ['checksum_sha256'],
        unique=False
    )
    op.create_index(
        'idx_files_created_at',
        'files',
        ['created_at'],
        unique=False
    )
    op.create_index(
        'idx_files_original_filename',
        'files',
        ['original_filename'],
        unique=False
    )
    # Partial index для TTL expiration (только temporary файлы без deleted_at)
    op.create_index(
        'idx_files_ttl_expires',
        'files',
        ['ttl_expires_at'],
        unique=False,
        postgresql_where=sa.text("retention_policy = 'temporary' AND deleted_at IS NULL")
    )
    # Partial index для активных файлов (не удалённых)
    op.create_index(
        'idx_files_active',
        'files',
        ['file_id'],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL")
    )

    # 2. Создаём таблицу file_finalize_transactions - лог Two-Phase Commit
    op.create_table(
        'file_finalize_transactions',
        sa.Column(
            'transaction_id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Уникальный UUID идентификатор транзакции финализации'
        ),
        sa.Column(
            'file_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='ID файла который финализируется'
        ),

        # Storage Elements
        sa.Column(
            'source_se',
            sa.String(255),
            nullable=False,
            comment='ID исходного Storage Element (Edit SE)'
        ),
        sa.Column(
            'target_se',
            sa.String(255),
            nullable=False,
            comment='ID целевого Storage Element (RW SE)'
        ),

        # Transaction Status
        sa.Column(
            'status',
            finalize_transaction_status_enum,
            nullable=False,
            server_default='copying',
            comment='Статус транзакции: copying, copied, verifying, completed, failed, rolled_back'
        ),

        # Checksums для verification
        sa.Column(
            'checksum_source',
            sa.String(64),
            nullable=True,
            comment='SHA-256 checksum файла на source SE'
        ),
        sa.Column(
            'checksum_target',
            sa.String(64),
            nullable=True,
            comment='SHA-256 checksum файла на target SE'
        ),

        # File details для tracking
        sa.Column(
            'file_size',
            sa.BigInteger(),
            nullable=True,
            comment='Размер файла в байтах (для verification)'
        ),

        # Error handling
        sa.Column(
            'error_message',
            sa.Text(),
            nullable=True,
            comment='Сообщение об ошибке (при status=failed)'
        ),
        sa.Column(
            'error_code',
            sa.String(50),
            nullable=True,
            comment='Код ошибки для categorization'
        ),
        sa.Column(
            'retry_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='Количество retry attempts'
        ),

        # Initiator tracking
        sa.Column(
            'initiated_by',
            sa.String(100),
            nullable=True,
            comment='Client ID или User ID инициировавший финализацию'
        ),

        # Timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment='Дата создания транзакции'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment='Дата последнего обновления'
        ),
        sa.Column(
            'completed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата завершения транзакции (success или failure)'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('transaction_id', name=op.f('pk_file_finalize_transactions')),
        sa.ForeignKeyConstraint(
            ['file_id'],
            ['files.file_id'],
            name=op.f('fk_file_finalize_transactions_file_id'),
            ondelete='CASCADE'
        ),
    )

    # Indexes для file_finalize_transactions
    op.create_index(
        'idx_file_finalize_tx_file_id',
        'file_finalize_transactions',
        ['file_id'],
        unique=False
    )
    op.create_index(
        'idx_file_finalize_tx_status',
        'file_finalize_transactions',
        ['status'],
        unique=False
    )
    op.create_index(
        'idx_file_finalize_tx_created',
        'file_finalize_transactions',
        ['created_at'],
        unique=False
    )
    # Partial index для pending transactions
    op.create_index(
        'idx_file_finalize_tx_pending',
        'file_finalize_transactions',
        ['transaction_id'],
        unique=False,
        postgresql_where=sa.text("status IN ('copying', 'copied', 'verifying')")
    )

    # 3. Создаём таблицу file_cleanup_queue - очередь для GC
    op.create_table(
        'file_cleanup_queue',
        sa.Column(
            'id',
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment='Уникальный ID записи в очереди'
        ),
        sa.Column(
            'file_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='ID файла для удаления'
        ),
        sa.Column(
            'storage_element_id',
            sa.String(255),
            nullable=False,
            comment='ID Storage Element где находится файл'
        ),
        sa.Column(
            'storage_path',
            sa.String(1000),
            nullable=True,
            comment='Путь к файлу в Storage Element'
        ),

        # Scheduling
        sa.Column(
            'scheduled_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='Дата когда файл должен быть удалён (e.g., +24h safety margin)'
        ),
        sa.Column(
            'priority',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='Приоритет в очереди (выше = раньше, default 0)'
        ),

        # Reason tracking
        sa.Column(
            'cleanup_reason',
            sa.String(50),
            nullable=False,
            comment='Причина: ttl_expired, finalized, orphaned, manual'
        ),

        # Processing status
        sa.Column(
            'processed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата когда cleanup был выполнен'
        ),
        sa.Column(
            'success',
            sa.Boolean(),
            nullable=True,
            comment='Успешность cleanup операции'
        ),
        sa.Column(
            'error_message',
            sa.Text(),
            nullable=True,
            comment='Сообщение об ошибке (если cleanup failed)'
        ),
        sa.Column(
            'retry_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='Количество retry attempts'
        ),

        # Timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment='Дата добавления в очередь'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('id', name=op.f('pk_file_cleanup_queue')),
    )

    # Indexes для file_cleanup_queue
    op.create_index(
        'idx_cleanup_queue_scheduled',
        'file_cleanup_queue',
        ['scheduled_at'],
        unique=False,
        postgresql_where=sa.text("processed_at IS NULL")
    )
    op.create_index(
        'idx_cleanup_queue_file_id',
        'file_cleanup_queue',
        ['file_id'],
        unique=False
    )
    op.create_index(
        'idx_cleanup_queue_storage_element',
        'file_cleanup_queue',
        ['storage_element_id'],
        unique=False
    )
    op.create_index(
        'idx_cleanup_queue_reason',
        'file_cleanup_queue',
        ['cleanup_reason'],
        unique=False
    )
    # Composite index для GC job (efficient query)
    op.create_index(
        'idx_cleanup_queue_pending',
        'file_cleanup_queue',
        ['scheduled_at', 'priority'],
        unique=False,
        postgresql_where=sa.text("processed_at IS NULL")
    )


def downgrade() -> None:
    """Drop retention policy and lifecycle management tables."""

    # Drop indexes
    op.drop_index('idx_cleanup_queue_pending', table_name='file_cleanup_queue')
    op.drop_index('idx_cleanup_queue_reason', table_name='file_cleanup_queue')
    op.drop_index('idx_cleanup_queue_storage_element', table_name='file_cleanup_queue')
    op.drop_index('idx_cleanup_queue_file_id', table_name='file_cleanup_queue')
    op.drop_index('idx_cleanup_queue_scheduled', table_name='file_cleanup_queue')

    op.drop_index('idx_file_finalize_tx_pending', table_name='file_finalize_transactions')
    op.drop_index('idx_file_finalize_tx_created', table_name='file_finalize_transactions')
    op.drop_index('idx_file_finalize_tx_status', table_name='file_finalize_transactions')
    op.drop_index('idx_file_finalize_tx_file_id', table_name='file_finalize_transactions')

    op.drop_index('idx_files_active', table_name='files')
    op.drop_index('idx_files_ttl_expires', table_name='files')
    op.drop_index('idx_files_original_filename', table_name='files')
    op.drop_index('idx_files_created_at', table_name='files')
    op.drop_index('idx_files_checksum', table_name='files')
    op.drop_index('idx_files_storage_element', table_name='files')
    op.drop_index('idx_files_retention_policy', table_name='files')

    # Drop tables (reverse order)
    op.drop_table('file_cleanup_queue')
    op.drop_table('file_finalize_transactions')
    op.drop_table('files')

    # Drop ENUM types
    sa.Enum(name='finalize_transaction_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='retention_policy_enum').drop(op.get_bind(), checkfirst=True)
