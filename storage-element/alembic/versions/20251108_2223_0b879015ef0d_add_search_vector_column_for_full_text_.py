"""Add search_vector column for full-text search

Revision ID: 0b879015ef0d
Revises:
Create Date: 2025-11-08 22:23:01.022365

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0b879015ef0d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Создание всех таблиц Storage Element и добавление search_vector column.

    Включает:
    - file_metadata table с full-text search support
    - wal table для транзакционного журнала
    - config table для runtime configuration
    """
    # Получаем table_prefix из переменной окружения или используем дефолтный
    import os
    table_prefix = os.getenv("APP__DATABASE__TABLE_PREFIX", "storage_elem_01")

    # Create file_metadata table
    op.create_table(
        f'{table_prefix}_file_metadata',
        sa.Column('file_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('storage_filename', sa.String(255), unique=True, nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('mime_type', sa.String(255)),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('uploaded_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('uploaded_by', sa.String(255), nullable=False),
        sa.Column('uploader_full_name', sa.String(500)),
        sa.Column('description', sa.Text()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('tags', postgresql.JSONB()),
        sa.Column('retention_days', sa.Integer(), nullable=False),
        sa.Column('retention_expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        # Full-text search vector column (PostgreSQL-specific)
        sa.Column('search_vector', postgresql.TSVECTOR()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),

        # Check constraints
        sa.CheckConstraint('file_size > 0', name='ck_file_size_positive'),
        sa.CheckConstraint('version >= 1', name='ck_version_minimum'),
        sa.CheckConstraint('retention_days > 0', name='ck_retention_positive'),
    )

    # Create indexes for file_metadata
    op.create_index('ix_uploaded_at', f'{table_prefix}_file_metadata', ['uploaded_at'])
    op.create_index('ix_uploaded_by', f'{table_prefix}_file_metadata', ['uploaded_by'])
    op.create_index('ix_retention_expires_at', f'{table_prefix}_file_metadata', ['retention_expires_at'])
    op.create_index('ix_sha256', f'{table_prefix}_file_metadata', ['sha256'])

    # GIN index for full-text search
    op.create_index(
        'ix_search_vector',
        f'{table_prefix}_file_metadata',
        ['search_vector'],
        postgresql_using='gin'
    )

    # Partial index для скоро истекающих файлов
    op.execute(f"""
        CREATE INDEX ix_expiring_soon ON {table_prefix}_file_metadata(retention_expires_at)
        WHERE retention_expires_at < (CURRENT_TIMESTAMP + INTERVAL '30 days')
    """)

    # Trigger для автоматического обновления search_vector
    op.execute(f"""
        CREATE OR REPLACE FUNCTION {table_prefix}_update_search_vector()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.original_filename, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(array_to_string(
                    ARRAY(SELECT jsonb_array_elements_text(NEW.tags)), ' '
                ), '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute(f"""
        CREATE TRIGGER trig_update_search_vector
        BEFORE INSERT OR UPDATE ON {table_prefix}_file_metadata
        FOR EACH ROW
        EXECUTE FUNCTION {table_prefix}_update_search_vector();
    """)

    # Create WAL table
    op.create_table(
        f'{table_prefix}_wal',
        sa.Column('wal_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column('saga_id', sa.String(255)),
        sa.Column('operation_type', sa.String(50), nullable=False),
        sa.Column('operation_status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('file_id', postgresql.UUID(as_uuid=True)),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('compensation_data', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('committed_at', sa.TIMESTAMP(timezone=True)),

        # Check constraints
        sa.CheckConstraint(
            "operation_type IN ('upload', 'delete', 'update_metadata', 'mode_change')",
            name='ck_operation_type'
        ),
        sa.CheckConstraint(
            "operation_status IN ('pending', 'in_progress', 'committed', 'rolled_back', 'failed')",
            name='ck_operation_status'
        ),
    )

    # Create indexes for WAL
    op.create_index('ix_wal_transaction_id', f'{table_prefix}_wal', ['transaction_id'])
    op.create_index('ix_wal_status', f'{table_prefix}_wal', ['operation_status'])
    op.create_index('ix_wal_created_at', f'{table_prefix}_wal', ['created_at'], postgresql_using='btree')
    op.create_index('ix_wal_saga_id', f'{table_prefix}_wal', ['saga_id'])

    # Partial index для незавершенных транзакций
    op.execute(f"""
        CREATE INDEX ix_wal_pending ON {table_prefix}_wal(operation_status)
        WHERE operation_status IN ('pending', 'in_progress')
    """)

    # GIN index для JSONB payload search
    op.create_index(
        'ix_wal_payload',
        f'{table_prefix}_wal',
        ['payload'],
        postgresql_using='gin'
    )

    # Create config table
    op.create_table(
        f'{table_prefix}_config',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True)),
    )


def downgrade() -> None:
    """
    Удаление всех таблиц Storage Element.
    """
    import os
    table_prefix = os.getenv("APP__DATABASE__TABLE_PREFIX", "storage_elem_01")

    # Drop trigger and function for search_vector
    op.execute(f"DROP TRIGGER IF EXISTS trig_update_search_vector ON {table_prefix}_file_metadata")
    op.execute(f"DROP FUNCTION IF EXISTS {table_prefix}_update_search_vector()")

    # Drop tables
    op.drop_table(f'{table_prefix}_config')
    op.drop_table(f'{table_prefix}_wal')
    op.drop_table(f'{table_prefix}_file_metadata')
