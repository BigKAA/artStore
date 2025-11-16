"""add_password_policy_fields

Revision ID: 20251116_1630_pwd_policy
Revises: 20251116_1200_audit
Create Date: 2025-11-16 16:30:00.000000

Добавление полей для Password Policy infrastructure в таблицу service_accounts:
- secret_history: JSONB поле для хранения последних 5 хешей паролей (предотвращение reuse)
- secret_changed_at: DateTime(TZ) поле для отслеживания времени последнего изменения пароля

Sprint 16 Phase 1: Strong Random Passwords with Password History enforcement.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20251116_1630_pwd_policy'
down_revision = '20251116_1200_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Добавление password policy полей в service_accounts таблицу.

    Изменения:
    1. secret_history: JSONB массив для хранения истории хешей паролей (max 5 items)
    2. secret_changed_at: Timestamp последнего изменения client_secret

    Data Migration:
    - Существующие Service Accounts получат пустую историю []
    - secret_changed_at инициализируется значением created_at (предполагаем, что пароль был установлен при создании)
    """

    # 1. Добавление secret_history (JSONB, nullable, default empty array)
    op.add_column(
        'service_accounts',
        sa.Column(
            'secret_history',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,  # Initially nullable для существующих записей
            comment='История последних 5 хешей client_secret для предотвращения reuse (JSON array)'
        )
    )

    # 2. Добавление secret_changed_at (DateTime(TZ), nullable)
    op.add_column(
        'service_accounts',
        sa.Column(
            'secret_changed_at',
            sa.DateTime(timezone=True),
            nullable=True,  # Initially nullable для существующих записей
            comment='Timestamp последнего изменения client_secret (для password aging)'
        )
    )

    # 3. Data Migration: Инициализация значений для существующих Service Accounts
    # Используем прямой SQL для обновления всех записей
    op.execute("""
        UPDATE service_accounts
        SET
            secret_history = '[]'::jsonb,  -- Пустой массив для всех существующих
            secret_changed_at = created_at  -- Предполагаем, что пароль установлен при создании
        WHERE secret_history IS NULL OR secret_changed_at IS NULL
    """)

    # 4. Изменение колонок на NOT NULL после backfill
    op.alter_column(
        'service_accounts',
        'secret_history',
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),  # Default для новых записей
        comment='История последних 5 хешей client_secret для предотвращения reuse (JSON array)'
    )

    op.alter_column(
        'service_accounts',
        'secret_changed_at',
        nullable=False,
        server_default=sa.text('NOW()'),  # Default для новых записей
        comment='Timestamp последнего изменения client_secret (для password aging)'
    )

    # 5. Создание индекса для быстрого поиска истекающих паролей
    # Этот индекс будет использоваться для фоновой задачи проверки password expiration
    op.create_index(
        'idx_service_accounts_secret_changed_at',
        'service_accounts',
        ['secret_changed_at'],
        unique=False
    )

    # 6. Composite index для password expiration checks
    # Для быстрого поиска активных Service Accounts с истекающими паролями
    op.create_index(
        'idx_service_accounts_password_expiry',
        'service_accounts',
        ['status', 'secret_changed_at'],
        unique=False,
        postgresql_where=sa.text("status = 'ACTIVE'")  # Partial index только для активных
    )


def downgrade() -> None:
    """
    Удаление password policy полей из service_accounts таблицы.

    ВНИМАНИЕ: Это приведет к потере всей истории паролей!
    """

    # 1. Удаление индексов
    op.drop_index(
        'idx_service_accounts_password_expiry',
        table_name='service_accounts'
    )
    op.drop_index(
        'idx_service_accounts_secret_changed_at',
        table_name='service_accounts'
    )

    # 2. Удаление колонок
    op.drop_column('service_accounts', 'secret_changed_at')
    op.drop_column('service_accounts', 'secret_history')
