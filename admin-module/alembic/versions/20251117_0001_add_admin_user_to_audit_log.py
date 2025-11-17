"""add admin_user_id to audit_log

Revision ID: add_admin_user_audit
Revises: create_admin_users
Create Date: 2025-11-17 00:01:00.000000

Добавление поля admin_user_id в таблицу audit_logs для поддержки
логирования действий администраторов Admin UI.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_admin_user_audit'
down_revision = 'create_admin_users'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Добавление admin_user_id поля в audit_logs.
    """
    # Добавление колонки admin_user_id
    op.add_column(
        'audit_logs',
        sa.Column(
            'admin_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('admin_users.id', ondelete='SET NULL'),
            nullable=True,
            comment='ID admin user (NULL для non-admin events)'
        )
    )

    # Создание индекса для производительности
    op.create_index(
        'idx_audit_logs_admin_user_id',
        'audit_logs',
        ['admin_user_id'],
        unique=False
    )


def downgrade() -> None:
    """
    Удаление admin_user_id поля из audit_logs.
    """
    # Удаление индекса
    op.drop_index('idx_audit_logs_admin_user_id', table_name='audit_logs')

    # Удаление колонки
    op.drop_column('audit_logs', 'admin_user_id')
