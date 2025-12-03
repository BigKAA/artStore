"""Consolidated schema initialization - Create all tables from scratch.

Revision ID: 20251126_0000
Revises:
Create Date: 2025-11-26 12:00:00.000000

This is a consolidated migration that creates the entire database schema from scratch.
It replaces multiple previous migrations and includes:
1. Removal of legacy User model (only AdminUser and ServiceAccount remain)
2. Addition of first_name, last_name, organization fields to AdminUser
3. Proper FK relationships in AuditLog table

Features:
- admin_users table with new fields (first_name, last_name, organization)
- service_accounts table with OAuth 2.0 credentials
- jwt_keys table for JWT key rotation
- storage_elements table for storage management
- audit_logs table with tamper-proof signatures

Roles:
- AdminRole: SUPER_ADMIN, ADMIN, READONLY
- ServiceAccountRole: ADMIN, USER, AUDITOR, READONLY
- StorageMode: edit, rw, ro, ar
- StorageType: hot, warm, cold
- StorageStatus: READY, INITIALIZING, UPGRADING, DEGRADED, OFFLINE
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '20251126_0000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the complete database schema from scratch."""

    # Define custom ENUM types (SQLAlchemy will create them automatically when tables are created)
    admin_role_enum = postgresql.ENUM('super_admin', 'admin', 'readonly', name='admin_role', create_type=True)
    service_account_role_enum = postgresql.ENUM('ADMIN', 'USER', 'AUDITOR', 'READONLY', name='service_account_role_enum', create_type=True)
    service_account_status_enum = postgresql.ENUM('ACTIVE', 'SUSPENDED', 'EXPIRED', 'DELETED', name='service_account_status_enum', create_type=True)
    storage_mode_enum = postgresql.ENUM('edit', 'rw', 'ro', 'ar', name='storage_mode_enum', create_type=True)
    storage_type_enum = postgresql.ENUM('local', 's3', name='storage_type_enum', create_type=True)
    storage_status_enum = postgresql.ENUM('online', 'offline', 'degraded', 'maintenance', name='storage_status_enum', create_type=True)

    # Note: Do NOT manually call .create() - SQLAlchemy will auto-create ENUMs when tables are created

    # Create admin_users table
    op.create_table(
        'admin_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False, comment='Уникальный UUID идентификатор Admin User'),
        sa.Column('username', sa.String(100), nullable=False, comment='Уникальное имя пользователя для логина'),
        sa.Column('email', sa.String(255), nullable=False, comment='Уникальный email адрес администратора'),
        sa.Column('first_name', sa.String(100), nullable=True, comment='Имя администратора'),
        sa.Column('last_name', sa.String(100), nullable=True, comment='Фамилия администратора'),
        sa.Column('organization', sa.String(200), nullable=True, comment='Организация, к которой принадлежит администратор'),
        sa.Column('password_hash', sa.String(255), nullable=False, comment='Bcrypt хеш пароля (work factor 12)'),
        sa.Column('password_history', postgresql.JSON, nullable=True, comment='История предыдущих password hashes (максимум 5)'),
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True, comment='Дата последней смены пароля'),
        sa.Column('role', admin_role_enum, nullable=False, server_default='admin', comment='Роль администратора в системе'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true(), comment='Флаг активности аккаунта (True = активен)'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false(), comment='Флаг системного Admin User (не может быть удален через API)'),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True, comment='Дата и время последнего успешного логина'),
        sa.Column('login_attempts', sa.Integer(), nullable=False, server_default='0', comment='Счетчик неудачных попыток логина (для rate limiting)'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True, comment='Дата до которой аккаунт заблокирован (после 5 неудачных попыток)'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='Дата создания'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='Дата обновления'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_users')),
        sa.UniqueConstraint('username', name=op.f('uq_admin_users_username')),
        sa.UniqueConstraint('email', name=op.f('uq_admin_users_email')),
    )

    op.create_index('idx_admin_users_username', 'admin_users', ['username'], unique=False)
    op.create_index('idx_admin_users_email', 'admin_users', ['email'], unique=False)
    op.create_index('idx_admin_users_enabled', 'admin_users', ['enabled'], unique=False)
    op.create_index('idx_admin_users_role', 'admin_users', ['role'], unique=False)
    op.create_index('idx_admin_users_last_login', 'admin_users', ['last_login_at'], unique=False)

    # Create service_accounts table
    op.create_table(
        'service_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False, comment='Уникальный UUID идентификатор Service Account'),
        sa.Column('client_id', sa.String(100), nullable=False, comment='Уникальный Client ID (формат: sa_env_name_random)'),
        sa.Column('client_secret_hash', sa.String(255), nullable=False, comment='Bcrypt хеш client secret (work factor 12)'),
        sa.Column('secret_history', postgresql.JSON, nullable=True, comment='История предыдущих client secret hashes (максимум 5)'),
        sa.Column('name', sa.String(100), nullable=False, comment='Человекочитаемое название Service Account'),
        sa.Column('description', sa.String(500), nullable=True, comment='Описание назначения Service Account'),
        sa.Column('role', service_account_role_enum, nullable=False, server_default='USER', comment='Роль Service Account (ADMIN, USER, AUDITOR, READONLY)'),
        sa.Column('status', service_account_status_enum, nullable=False, server_default='ACTIVE', comment='Статус Service Account'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false(), comment='Флаг системного Service Account (не может быть удален через API)'),
        sa.Column('rate_limit', sa.Integer(), nullable=False, server_default='100', comment='Rate limit: requests per minute (default: 100)'),
        sa.Column('secret_expires_at', sa.DateTime(timezone=True), nullable=True, comment='Дата истечения текущего client secret (90 дней)'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='Дата создания'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='Дата обновления'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_service_accounts')),
        sa.UniqueConstraint('client_id', name=op.f('uq_service_accounts_client_id')),
        sa.UniqueConstraint('name', name=op.f('uq_service_accounts_name')),
    )

    op.create_index('idx_service_accounts_client_id', 'service_accounts', ['client_id'], unique=False)
    op.create_index('idx_service_accounts_name', 'service_accounts', ['name'], unique=False)
    op.create_index('idx_service_accounts_status', 'service_accounts', ['status'], unique=False)
    op.create_index('idx_service_accounts_role', 'service_accounts', ['role'], unique=False)

    # Create jwt_keys table
    op.create_table(
        'jwt_keys',
        sa.Column('id', sa.Integer(), nullable=False, comment='Unique JWT key identifier'),
        sa.Column('kid', sa.String(100), nullable=False, comment='Key ID (format: artstore_prod_YYYYMMDD_HHMMSS)'),
        sa.Column('private_key', sa.Text(), nullable=False, comment='Private key in PEM format (encrypted in production)'),
        sa.Column('public_key', sa.Text(), nullable=False, comment='Public key in PEM format (used by other services for JWT verification)'),
        sa.Column('algorithm', sa.String(20), nullable=False, server_default='RS256', comment='Algorithm: RS256 (RSA with SHA-256)'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true(), comment='Is this the current active key for signing'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='Дата создания ключа'),
        sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True, comment='Дата ротации ключа (если применимо)'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, comment='Дата истечения ключа (старые ключи сохраняются для verification)'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_jwt_keys')),
        sa.UniqueConstraint('kid', name=op.f('uq_jwt_keys_kid')),
    )

    op.create_index('idx_jwt_keys_is_active', 'jwt_keys', ['is_active'], unique=False)
    op.create_index('idx_jwt_keys_kid', 'jwt_keys', ['kid'], unique=False)

    # Create storage_elements table
    # Схема соответствует модели StorageElement из app/models/storage_element.py
    op.create_table(
        'storage_elements',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Уникальный идентификатор Storage Element'),
        sa.Column('element_id', sa.String(50), nullable=True, comment='Уникальный строковый ID для Redis Registry (например: se-01)'),
        sa.Column('name', sa.String(100), nullable=False, comment='Человекочитаемое имя storage element (уникальное)'),
        sa.Column('description', sa.String(500), nullable=True, comment='Описание хранилища'),
        sa.Column('mode', storage_mode_enum, nullable=False, server_default='edit', comment='Режим работы storage element'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100', comment='Приоритет для Sequential Fill алгоритма (меньше = выше приоритет)'),
        sa.Column('storage_type', storage_type_enum, nullable=False, server_default='local', comment='Тип физического хранилища'),
        sa.Column('base_path', sa.String(500), nullable=False, comment='Базовый путь (local) или bucket name (s3)'),
        sa.Column('api_url', sa.String(255), nullable=False, comment='URL для API доступа к storage element'),
        sa.Column('api_key', sa.String(255), nullable=True, comment='API ключ для аутентификации (хешированный)'),
        sa.Column('status', storage_status_enum, nullable=False, server_default='online', comment='Текущий статус storage element'),
        sa.Column('capacity_bytes', sa.BigInteger(), nullable=True, comment='Общая емкость в байтах'),
        sa.Column('used_bytes', sa.BigInteger(), nullable=False, server_default='0', comment='Использовано байтов'),
        sa.Column('file_count', sa.Integer(), nullable=False, server_default='0', comment='Количество файлов'),
        sa.Column('retention_days', sa.Integer(), nullable=True, comment='Срок хранения файлов в днях (None = бессрочно)'),
        sa.Column('last_health_check', sa.DateTime(timezone=True), nullable=True, comment='Время последней проверки health'),
        sa.Column('is_replicated', sa.Boolean(), nullable=False, server_default=sa.false(), comment='Флаг репликации'),
        sa.Column('replica_count', sa.Integer(), nullable=False, server_default='0', comment='Количество реплик'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='Дата создания'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='Дата обновления'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_storage_elements')),
        sa.UniqueConstraint('name', name=op.f('uq_storage_elements_name')),
        sa.UniqueConstraint('element_id', name=op.f('uq_storage_elements_element_id')),
    )

    op.create_index('idx_storage_elements_name', 'storage_elements', ['name'], unique=False)
    op.create_index('idx_storage_elements_element_id', 'storage_elements', ['element_id'], unique=True)
    op.create_index('idx_storage_elements_mode', 'storage_elements', ['mode'], unique=False)
    op.create_index('idx_storage_elements_status', 'storage_elements', ['status'], unique=False)
    op.create_index('idx_storage_mode_status', 'storage_elements', ['mode', 'status'], unique=False)
    op.create_index('idx_storage_mode_priority', 'storage_elements', ['mode', 'priority'], unique=False)

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='Уникальный идентификатор audit log entry'),
        sa.Column('event_type', sa.String(100), nullable=False, comment='Тип security события'),
        sa.Column('severity', sa.String(20), nullable=False, server_default='info', comment='Severity level: debug, info, warning, error, critical'),
        sa.Column('service_account_id', postgresql.UUID(as_uuid=True), nullable=True, comment='ID service account (NULL для non-service-account events)'),
        sa.Column('admin_user_id', postgresql.UUID(as_uuid=True), nullable=True, comment='ID admin user (NULL для non-admin events)'),
        sa.Column('actor_type', sa.String(20), nullable=False, comment='Тип актора: service_account, admin_user, system'),
        sa.Column('resource_type', sa.String(50), nullable=True, comment='Тип ресурса: service_account, jwt_key, storage_element'),
        sa.Column('resource_id', sa.String(100), nullable=True, comment='ID затронутого ресурса'),
        sa.Column('action', sa.String(50), nullable=False, comment='Действие: create, read, update, delete, rotate, login, logout'),
        sa.Column('ip_address', sa.String(45), nullable=True, comment='IP адрес клиента (IPv4 или IPv6)'),
        sa.Column('user_agent', sa.Text(), nullable=True, comment='User agent string'),
        sa.Column('request_id', sa.String(36), nullable=True, comment='Correlation ID для трассировки (OpenTelemetry trace_id)'),
        sa.Column('session_id', sa.String(100), nullable=True, comment='Session identifier для корреляции событий'),
        sa.Column('data', postgresql.JSONB(), nullable=True, comment='Дополнительные данные события (JSON format)'),
        sa.Column('success', sa.Boolean(), nullable=False, comment='Успешность операции'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Текст ошибки (если success=false)'),
        sa.Column('hmac_signature', sa.String(64), nullable=False, comment='HMAC-SHA256 signature для защиты от изменения'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='Timestamp события'),
        sa.ForeignKeyConstraint(['admin_user_id'], ['admin_users.id'], name=op.f('fk_audit_logs_admin_user_id'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['service_account_id'], ['service_accounts.id'], name=op.f('fk_audit_logs_service_account_id'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs')),
    )

    op.create_index('idx_audit_logs_event_type', 'audit_logs', ['event_type'], unique=False)
    op.create_index('idx_audit_logs_severity', 'audit_logs', ['severity'], unique=False)
    op.create_index('idx_audit_logs_request_id', 'audit_logs', ['request_id'], unique=False)
    op.create_index('idx_audit_logs_success', 'audit_logs', ['success'], unique=False)
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('idx_audit_logs_admin_user_id', 'audit_logs', ['admin_user_id'], unique=False)
    op.create_index('idx_audit_logs_service_account_id', 'audit_logs', ['service_account_id'], unique=False)


def downgrade() -> None:
    """Drop all tables and types."""

    # Drop indexes (explicit drops for clarity)
    op.drop_index('idx_audit_logs_service_account_id', table_name='audit_logs')
    op.drop_index('idx_audit_logs_admin_user_id', table_name='audit_logs')
    op.drop_index('idx_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('idx_audit_logs_success', table_name='audit_logs')
    op.drop_index('idx_audit_logs_request_id', table_name='audit_logs')
    op.drop_index('idx_audit_logs_severity', table_name='audit_logs')
    op.drop_index('idx_audit_logs_event_type', table_name='audit_logs')

    op.drop_index('idx_storage_mode_priority', table_name='storage_elements')
    op.drop_index('idx_storage_mode_status', table_name='storage_elements')
    op.drop_index('idx_storage_elements_status', table_name='storage_elements')
    op.drop_index('idx_storage_elements_mode', table_name='storage_elements')
    op.drop_index('idx_storage_elements_element_id', table_name='storage_elements')
    op.drop_index('idx_storage_elements_name', table_name='storage_elements')

    op.drop_index('idx_jwt_keys_kid', table_name='jwt_keys')
    op.drop_index('idx_jwt_keys_is_active', table_name='jwt_keys')

    op.drop_index('idx_service_accounts_role', table_name='service_accounts')
    op.drop_index('idx_service_accounts_status', table_name='service_accounts')
    op.drop_index('idx_service_accounts_name', table_name='service_accounts')
    op.drop_index('idx_service_accounts_client_id', table_name='service_accounts')

    op.drop_index('idx_admin_users_last_login', table_name='admin_users')
    op.drop_index('idx_admin_users_role', table_name='admin_users')
    op.drop_index('idx_admin_users_enabled', table_name='admin_users')
    op.drop_index('idx_admin_users_email', table_name='admin_users')
    op.drop_index('idx_admin_users_username', table_name='admin_users')

    # Drop tables (in reverse order of creation)
    op.drop_table('audit_logs')
    op.drop_table('storage_elements')
    op.drop_table('jwt_keys')
    op.drop_table('service_accounts')
    op.drop_table('admin_users')

    # Drop custom ENUM types
    sa.Enum(name='storage_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='storage_type_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='storage_mode_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='service_account_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='service_account_role_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='admin_role').drop(op.get_bind(), checkfirst=True)
