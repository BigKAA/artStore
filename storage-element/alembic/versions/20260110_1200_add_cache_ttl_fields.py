"""add_cache_ttl_fields

Revision ID: a1b2c3d4e5f6
Revises: 0b879015ef0d
Create Date: 2026-01-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '0b879015ef0d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Добавление cache TTL полей в FileMetadata таблицу.

    Поля:
    - cache_updated_at: Timestamp последнего обновления кеша из attr.json
    - cache_ttl_hours: TTL кеша в часах (24 для edit/rw, 168 для ro/ar)
    """
    # Получаем table_prefix из переменной окружения или используем дефолтный
    import os
    table_prefix = os.getenv("APP__DATABASE__TABLE_PREFIX", "storage_elem_01")
    table_name = f'{table_prefix}_files'

    # Добавление cache_updated_at
    op.add_column(
        table_name,
        sa.Column(
            'cache_updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment='Timestamp последнего обновления кеша из attr.json'
        )
    )

    # Добавление cache_ttl_hours
    op.add_column(
        table_name,
        sa.Column(
            'cache_ttl_hours',
            sa.Integer(),
            nullable=False,
            server_default='24',
            comment='TTL кеша в часах (24=edit/rw, 168=ro/ar)'
        )
    )


def downgrade() -> None:
    """
    Откат миграции - удаление cache TTL полей.
    """
    import os
    table_prefix = os.getenv("APP__DATABASE__TABLE_PREFIX", "storage_elem_01")
    table_name = f'{table_prefix}_files'

    op.drop_column(table_name, 'cache_ttl_hours')
    op.drop_column(table_name, 'cache_updated_at')
