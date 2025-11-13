"""add_service_accounts_table

Revision ID: 20251113_2127_sa
Revises: 0df874976374
Create Date: 2025-11-13 21:27:00.000000

Добавление таблицы service_accounts для OAuth 2.0 Client Credentials authentication.
Service Accounts заменяют User model с LDAP интеграцией для machine-to-machine аутентификации.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision = '20251113_2127_sa'
down_revision = '0df874976374'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создание таблицы service_accounts."""

    # Создание ENUM типов для ролей и статусов
    service_account_role_enum = postgresql.ENUM(
        'ADMIN', 'USER', 'AUDITOR', 'READONLY',
        name='service_account_role_enum',
        create_type=True
    )

    service_account_status_enum = postgresql.ENUM(
        'ACTIVE', 'SUSPENDED', 'EXPIRED', 'DELETED',
        name='service_account_status_enum',
        create_type=True
    )

    # Создание таблицы service_accounts
    op.create_table(
        'service_accounts',
        # Primary Key - UUID
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
            nullable=False,
            comment='Уникальный UUID идентификатор Service Account'
        ),

        # Basic Information
        sa.Column(
            'name',
            sa.String(length=200),
            nullable=False,
            unique=True,
            comment='Человекочитаемое название Service Account'
        ),
        sa.Column(
            'description',
            sa.String(length=500),
            nullable=True,
            comment='Описание назначения Service Account'
        ),

        # OAuth 2.0 Client Credentials
        sa.Column(
            'client_id',
            sa.String(length=100),
            nullable=False,
            unique=True,
            comment='Уникальный client_id для OAuth 2.0 (формат: sa_<environment>_<name>_<random>)'
        ),
        sa.Column(
            'client_secret_hash',
            sa.String(length=255),
            nullable=False,
            comment='Bcrypt хеш client_secret (минимум 32 символа)'
        ),

        # Authorization
        sa.Column(
            'role',
            service_account_role_enum,
            nullable=False,
            server_default='USER',
            comment='Роль Service Account в системе'
        ),
        sa.Column(
            'status',
            service_account_status_enum,
            nullable=False,
            server_default='ACTIVE',
            comment='Текущий статус Service Account'
        ),
        sa.Column(
            'is_system',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Флаг системного Service Account (не может быть удален)'
        ),

        # Rate Limiting
        sa.Column(
            'rate_limit',
            sa.Integer(),
            nullable=False,
            server_default='100',
            comment='Лимит запросов в минуту (default 100 req/min)'
        ),

        # Secret Management
        sa.Column(
            'secret_expires_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='Дата истечения срока действия client_secret (автоматическая ротация каждые 90 дней)'
        ),

        # Usage Tracking
        sa.Column(
            'last_used_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата и время последнего использования (последний успешный /api/auth/token)'
        ),

        # Timestamps (TimestampMixin)
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('NOW()'),
            comment='Дата и время создания записи'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('NOW()'),
            comment='Дата и время последнего обновления записи'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_service_account_name'),
        sa.UniqueConstraint('client_id', name='uq_service_account_client_id'),
    )

    # Создание индексов для производительности
    op.create_index(
        'idx_service_account_status_role',
        'service_accounts',
        ['status', 'role'],
        unique=False
    )
    op.create_index(
        'idx_service_account_client_id',
        'service_accounts',
        ['client_id'],
        unique=True
    )
    op.create_index(
        'idx_service_account_secret_expiry',
        'service_accounts',
        ['secret_expires_at'],
        unique=False
    )
    op.create_index(
        op.f('ix_service_accounts_name'),
        'service_accounts',
        ['name'],
        unique=True
    )
    op.create_index(
        op.f('ix_service_accounts_status'),
        'service_accounts',
        ['status'],
        unique=False
    )


def downgrade() -> None:
    """Удаление таблицы service_accounts."""

    # Удаление индексов
    op.drop_index(op.f('ix_service_accounts_status'), table_name='service_accounts')
    op.drop_index(op.f('ix_service_accounts_name'), table_name='service_accounts')
    op.drop_index('idx_service_account_secret_expiry', table_name='service_accounts')
    op.drop_index('idx_service_account_client_id', table_name='service_accounts')
    op.drop_index('idx_service_account_status_role', table_name='service_accounts')

    # Удаление таблицы
    op.drop_table('service_accounts')

    # Удаление ENUM типов
    sa.Enum(name='service_account_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='service_account_role_enum').drop(op.get_bind(), checkfirst=True)
