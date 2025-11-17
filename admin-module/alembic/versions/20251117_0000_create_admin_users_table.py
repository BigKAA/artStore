"""create admin_users table

Revision ID: create_admin_users
Revises: 4c7e84fcc6b9
Create Date: 2025-11-17 00:00:00.000000

Создание таблицы admin_users для аутентификации администраторов Admin UI.
Admin Users используют login/password аутентификацию, отдельно от Service Accounts.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'create_admin_users'
down_revision = '4c7e84fcc6b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Создание таблицы admin_users и необходимых индексов.
    """
    # Создание enum типа для ролей администраторов
    admin_role_enum = postgresql.ENUM(
        'super_admin', 'admin', 'readonly',
        name='admin_role',
        create_type=True
    )

    # Создание таблицы admin_users
    op.create_table(
        'admin_users',
        # Primary key
        sa.Column(
            'id',
            sa.Uuid(),
            nullable=False,
            comment='Уникальный UUID идентификатор Admin User'
        ),

        # Credentials
        sa.Column(
            'username',
            sa.String(length=100),
            nullable=False,
            comment='Уникальное имя пользователя для логина'
        ),
        sa.Column(
            'email',
            sa.String(length=255),
            nullable=False,
            comment='Уникальный email адрес администратора'
        ),
        sa.Column(
            'password_hash',
            sa.String(length=255),
            nullable=False,
            comment='Bcrypt хеш пароля (work factor 12)'
        ),

        # Password security tracking
        sa.Column(
            'password_history',
            sa.JSON(),
            nullable=True,
            comment='История предыдущих password hashes (максимум 5)'
        ),
        sa.Column(
            'password_changed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата последней смены пароля'
        ),

        # Role and status
        sa.Column(
            'role',
            admin_role_enum,
            nullable=False,
            server_default='admin',
            comment='Роль администратора в системе'
        ),
        sa.Column(
            'enabled',
            sa.Boolean(),
            nullable=False,
            server_default='true',
            comment='Флаг активности аккаунта (True = активен)'
        ),
        sa.Column(
            'is_system',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Флаг системного Admin User (не может быть удален через API)'
        ),

        # Login tracking
        sa.Column(
            'last_login_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата и время последнего успешного логина'
        ),
        sa.Column(
            'login_attempts',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='Счетчик неудачных попыток логина (для rate limiting)'
        ),
        sa.Column(
            'locked_until',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Дата до которой аккаунт заблокирован (после 5 неудачных попыток)'
        ),

        # Timestamps (TimestampMixin pattern)
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Дата и время создания записи'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Дата и время последнего обновления записи'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', name='uq_admin_users_username'),
        sa.UniqueConstraint('email', name='uq_admin_users_email'),
    )

    # Создание индексов для производительности
    op.create_index(
        'idx_admin_users_username',
        'admin_users',
        ['username'],
        unique=False
    )
    op.create_index(
        'idx_admin_users_email',
        'admin_users',
        ['email'],
        unique=False
    )
    op.create_index(
        'idx_admin_users_enabled',
        'admin_users',
        ['enabled'],
        unique=False
    )
    op.create_index(
        'idx_admin_users_role',
        'admin_users',
        ['role'],
        unique=False
    )
    op.create_index(
        'idx_admin_users_last_login',
        'admin_users',
        ['last_login_at'],
        unique=False
    )


def downgrade() -> None:
    """
    Удаление таблицы admin_users и связанных объектов.
    """
    # Удаление индексов
    op.drop_index('idx_admin_users_last_login', table_name='admin_users')
    op.drop_index('idx_admin_users_role', table_name='admin_users')
    op.drop_index('idx_admin_users_enabled', table_name='admin_users')
    op.drop_index('idx_admin_users_email', table_name='admin_users')
    op.drop_index('idx_admin_users_username', table_name='admin_users')

    # Удаление таблицы
    op.drop_table('admin_users')

    # Удаление enum типа
    admin_role_enum = postgresql.ENUM(
        'super_admin', 'admin', 'readonly',
        name='admin_role'
    )
    admin_role_enum.drop(op.get_bind())
