"""remove_ldap_fields

Revision ID: remove_ldap_20251125
Revises: 20251117_0001_add_admin_user_to_audit_log
Create Date: 2025-11-25 14:54:00.000000

Удаление LDAP-связанных полей и индексов после Sprint 13.
- Удаление колонки ldap_dn из таблицы users
- Удаление индексов idx_user_ldap_lookup и ix_users_ldap_dn
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_ldap_20251125'
down_revision = '20251117_0001_add_admin_user_to_audit_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Удаление LDAP полей и индексов."""
    # Удаление индексов
    op.drop_index('idx_user_ldap_lookup', table_name='users')
    op.drop_index(op.f('ix_users_ldap_dn'), table_name='users')

    # Удаление колонки ldap_dn
    op.drop_column('users', 'ldap_dn')


def downgrade() -> None:
    """Восстановление LDAP полей и индексов (для rollback)."""
    # Восстановление колонки ldap_dn
    op.add_column('users', sa.Column(
        'ldap_dn',
        sa.String(length=500),
        nullable=True,
        comment='DEPRECATED: Поле не используется после Sprint 13 (LDAP removal)'
    ))

    # Восстановление индексов
    op.create_index(
        op.f('ix_users_ldap_dn'),
        'users',
        ['ldap_dn'],
        unique=True
    )
    op.create_index(
        'idx_user_ldap_lookup',
        'users',
        ['ldap_dn'],
        unique=False,
        postgresql_where=sa.text('ldap_dn IS NOT NULL')
    )
