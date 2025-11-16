"""add_jwt_key_rotation

Revision ID: 20251115_1600_jwt
Revises: 20251113_2127_sa
Create Date: 2025-11-15 16:00:00.000000

Добавление таблицы jwt_keys для автоматической ротации JWT ключей.
Поддержка graceful transition period (25h validity = 24h + 1h overlap).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20251115_1600_jwt'
down_revision = '20251113_2127_sa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создание таблицы jwt_keys для key rotation."""

    # Создание таблицы jwt_keys
    op.create_table(
        'jwt_keys',
        # Primary Key
        sa.Column(
            'id',
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
            comment='Уникальный идентификатор JWT key version'
        ),

        # Version UUID
        sa.Column(
            'version',
            sa.String(length=36),
            nullable=False,
            unique=True,
            comment='UUID version identifier для JWT key'
        ),

        # Cryptographic Keys
        sa.Column(
            'private_key',
            sa.Text(),
            nullable=False,
            comment='RSA private key (PEM format, 2048-bit)'
        ),
        sa.Column(
            'public_key',
            sa.Text(),
            nullable=False,
            comment='RSA public key (PEM format, 2048-bit)'
        ),

        # Algorithm
        sa.Column(
            'algorithm',
            sa.String(length=10),
            nullable=False,
            server_default='RS256',
            comment='JWT signing algorithm (RS256 only)'
        ),

        # Lifecycle Timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('NOW()'),
            comment='Key creation timestamp'
        ),
        sa.Column(
            'expires_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='Key expiration timestamp (25h = 24h + 1h grace period)'
        ),

        # Status
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default='true',
            comment='Active status flag (false = expired/deactivated)'
        ),

        # Rotation Metadata
        sa.Column(
            'rotation_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='Number of times this key has been part of rotation cycle'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version', name='uq_jwt_key_version'),
    )

    # Индексы для производительности
    op.create_index(
        'idx_jwt_keys_active',
        'jwt_keys',
        ['is_active'],
        unique=False
    )
    op.create_index(
        'idx_jwt_keys_expires_at',
        'jwt_keys',
        ['expires_at'],
        unique=False
    )
    op.create_index(
        'idx_jwt_keys_active_version',
        'jwt_keys',
        ['is_active', 'version'],
        unique=False
    )

    # Composite index для fast active key lookup
    op.create_index(
        'idx_jwt_keys_active_expires',
        'jwt_keys',
        ['is_active', 'expires_at'],
        unique=False
    )


def downgrade() -> None:
    """Удаление таблицы jwt_keys."""

    # Удаление индексов
    op.drop_index('idx_jwt_keys_active_expires', table_name='jwt_keys')
    op.drop_index('idx_jwt_keys_active_version', table_name='jwt_keys')
    op.drop_index('idx_jwt_keys_expires_at', table_name='jwt_keys')
    op.drop_index('idx_jwt_keys_active', table_name='jwt_keys')

    # Удаление таблицы
    op.drop_table('jwt_keys')
