"""add_audit_logging

Revision ID: 20251116_1200_audit
Revises: 20251115_1600_jwt
Create Date: 2025-11-16 12:00:00.000000

Добавление таблицы audit_logs для комплексного аудита безопасности.
Поддержка HMAC подписей для защиты от tampering.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20251116_1200_audit'
down_revision = '20251115_1600_jwt'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Создание таблицы audit_logs для security audit trail."""

    # Создание таблицы audit_logs
    op.create_table(
        'audit_logs',
        # Primary Key
        sa.Column(
            'id',
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
            comment='Уникальный идентификатор audit log entry'
        ),

        # Event Classification
        sa.Column(
            'event_type',
            sa.String(length=100),
            nullable=False,
            comment='Тип security события (login_success, jwt_rotation, etc.)'
        ),
        sa.Column(
            'severity',
            sa.String(length=20),
            nullable=False,
            server_default='info',
            comment='Severity level: debug, info, warning, error, critical'
        ),

        # Actor Information
        sa.Column(
            'user_id',
            sa.Integer(),
            nullable=True,
            comment='ID пользователя (NULL для system events)'
        ),
        sa.Column(
            'service_account_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='ID service account (NULL для user events)'
        ),
        sa.Column(
            'actor_type',
            sa.String(length=20),
            nullable=False,
            comment='Тип актора: user, service_account, system'
        ),

        # Resource Information
        sa.Column(
            'resource_type',
            sa.String(length=50),
            nullable=True,
            comment='Тип ресурса: user, service_account, jwt_key, storage_element'
        ),
        sa.Column(
            'resource_id',
            sa.String(length=100),
            nullable=True,
            comment='ID затронутого ресурса'
        ),
        sa.Column(
            'action',
            sa.String(length=50),
            nullable=False,
            comment='Действие: create, read, update, delete, rotate, login, logout'
        ),

        # Request Context
        sa.Column(
            'ip_address',
            sa.String(length=45),
            nullable=True,
            comment='IP адрес клиента (IPv4 или IPv6)'
        ),
        sa.Column(
            'user_agent',
            sa.Text(),
            nullable=True,
            comment='User agent string'
        ),
        sa.Column(
            'request_id',
            sa.String(length=36),
            nullable=True,
            comment='Correlation ID для трассировки (OpenTelemetry trace_id)'
        ),
        sa.Column(
            'session_id',
            sa.String(length=100),
            nullable=True,
            comment='Session identifier для корреляции событий'
        ),

        # Event Data
        sa.Column(
            'data',
            postgresql.JSONB(),
            nullable=True,
            comment='Дополнительные данные события (JSON format)'
        ),
        sa.Column(
            'success',
            sa.Boolean(),
            nullable=False,
            comment='Успешность операции (true/false)'
        ),
        sa.Column(
            'error_message',
            sa.Text(),
            nullable=True,
            comment='Текст ошибки (если success=false)'
        ),

        # Tamper Protection
        sa.Column(
            'hmac_signature',
            sa.String(length=64),
            nullable=False,
            comment='HMAC-SHA256 signature для защиты от изменения'
        ),

        # Timestamp
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('NOW()'),
            index=True,
            comment='Timestamp события'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
    )

    # Индексы для производительности поиска
    op.create_index(
        'idx_audit_logs_event_type',
        'audit_logs',
        ['event_type'],
        unique=False
    )
    op.create_index(
        'idx_audit_logs_user_id',
        'audit_logs',
        ['user_id'],
        unique=False
    )
    op.create_index(
        'idx_audit_logs_service_account_id',
        'audit_logs',
        ['service_account_id'],
        unique=False
    )
    op.create_index(
        'idx_audit_logs_resource',
        'audit_logs',
        ['resource_type', 'resource_id'],
        unique=False
    )
    op.create_index(
        'idx_audit_logs_severity',
        'audit_logs',
        ['severity'],
        unique=False
    )
    op.create_index(
        'idx_audit_logs_success',
        'audit_logs',
        ['success'],
        unique=False
    )
    op.create_index(
        'idx_audit_logs_request_id',
        'audit_logs',
        ['request_id'],
        unique=False
    )

    # Composite index для fast filtering by actor and time
    op.create_index(
        'idx_audit_logs_actor_time',
        'audit_logs',
        ['actor_type', 'created_at'],
        unique=False
    )

    # Composite index для security monitoring
    op.create_index(
        'idx_audit_logs_security',
        'audit_logs',
        ['severity', 'success', 'created_at'],
        unique=False
    )

    # Foreign keys
    op.create_foreign_key(
        'fk_audit_logs_user',
        'audit_logs',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_audit_logs_service_account',
        'audit_logs',
        'service_accounts',
        ['service_account_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Удаление таблицы audit_logs."""

    # Удаление foreign keys
    op.drop_constraint('fk_audit_logs_service_account', 'audit_logs', type_='foreignkey')
    op.drop_constraint('fk_audit_logs_user', 'audit_logs', type_='foreignkey')

    # Удаление индексов
    op.drop_index('idx_audit_logs_security', table_name='audit_logs')
    op.drop_index('idx_audit_logs_actor_time', table_name='audit_logs')
    op.drop_index('idx_audit_logs_request_id', table_name='audit_logs')
    op.drop_index('idx_audit_logs_success', table_name='audit_logs')
    op.drop_index('idx_audit_logs_severity', table_name='audit_logs')
    op.drop_index('idx_audit_logs_resource', table_name='audit_logs')
    op.drop_index('idx_audit_logs_service_account_id', table_name='audit_logs')
    op.drop_index('idx_audit_logs_user_id', table_name='audit_logs')
    op.drop_index('idx_audit_logs_event_type', table_name='audit_logs')

    # Удаление таблицы
    op.drop_table('audit_logs')
