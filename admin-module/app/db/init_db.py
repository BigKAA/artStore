"""
Database initialization functions.

Includes:
- Initial admin user creation
- Database schema initialization
- Data seeding for first-time setup
"""

import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.admin_user import AdminUser, AdminRole
from app.models.service_account import ServiceAccount, ServiceAccountRole, ServiceAccountStatus
from app.services.admin_auth_service import AdminAuthService
from app.services.service_account_service import ServiceAccountService

logger = logging.getLogger(__name__)


async def create_initial_admin_user(settings: Settings, db: AsyncSession) -> None:
    """
    Создание начального Admin User для Admin UI при первом запуске.

    Выполняется только если:
    - В базе данных нет admin_users
    - Конфигурация initial_admin.enabled = True

    Args:
        settings: Настройки приложения
        db: Async database session

    Note:
        Admin User используется для аутентификации в Admin UI через login/password.
        Использует переменные окружения INITIAL_ADMIN_*:
        - INITIAL_ADMIN_ENABLED: включить/выключить создание (default: true)
        - INITIAL_ADMIN_USERNAME: username для логина (default: "admin")
        - INITIAL_ADMIN_PASSWORD: пароль (default: "ChangeMe123!")
        - INITIAL_ADMIN_EMAIL: email адрес (default: "admin@artstore.local")
        - INITIAL_ADMIN_FIRSTNAME: имя администратора (опционально)
        - INITIAL_ADMIN_LASTNAME: фамилия администратора (опционально)

    Examples:
        >>> async with get_db_session() as db:
        ...     await create_initial_admin_user(settings, db)
    """
    # Проверка что initial admin создание включено
    if not settings.initial_admin.enabled:
        logger.info("Initial admin user creation disabled in configuration")
        return

    try:
        # Проверка существования admin users в БД
        result = await db.execute(select(func.count()).select_from(AdminUser))
        admin_count = result.scalar()

        if admin_count > 0:
            logger.debug(f"Admin users already exist in database (count: {admin_count}), skipping initial admin user creation")
            return

        # Создание initial admin user
        logger.info(
            "No admin users found in database, creating initial admin user for Admin UI",
            extra={
                "username": settings.initial_admin.username,
                "email": settings.initial_admin.email
            }
        )

        # Хеширование пароля
        admin_auth_service = AdminAuthService()
        password_hash = admin_auth_service.hash_password(settings.initial_admin.password)

        # Создание AdminUser объекта с использованием конфигурации
        initial_admin = AdminUser(
            username=settings.initial_admin.username,
            email=settings.initial_admin.email,
            password_hash=password_hash,
            first_name=settings.initial_admin.firstname or None,
            last_name=settings.initial_admin.lastname or None,
            organization="ArtStore",  # Default value
            role=AdminRole.SUPER_ADMIN,  # Первый admin всегда SUPER_ADMIN
            enabled=True,
            is_system=True  # System admin не может быть удален через API
        )

        db.add(initial_admin)
        await db.commit()
        await db.refresh(initial_admin)

        logger.info(
            "Initial admin user created successfully",
            extra={
                "admin_user_id": str(initial_admin.id),
                "username": initial_admin.username,
                "email": initial_admin.email,
                "role": initial_admin.role.value
            }
        )

        # CRITICAL SECURITY WARNING
        logger.warning(
            "SECURITY AUDIT: Initial admin user was automatically created with default password. "
            "Please change the password IMMEDIATELY through POST /api/v1/admin-auth/change-password endpoint. "
            "Default credentials: username='admin', password='admin123'",
            extra={
                "event": "initial_admin_user_created",
                "admin_user_id": str(initial_admin.id),
                "username": initial_admin.username,
                "security_risk": "high"
            }
        )

    except Exception as e:
        logger.error(
            f"Failed to create initial admin user: {e}",
            exc_info=True,
            extra={"error": str(e)}
        )
        await db.rollback()
        raise


async def create_initial_service_account(settings: Settings, db: AsyncSession) -> None:
    """
    Создание начального Service Account при первом запуске.

    Если INITIAL_ACCOUNT_PASSWORD не задан - генерирует автоматически,
    сохраняет в БД и выводит plain text secret в логи.
    Если Service Account уже существует - ничего не делает.

    Выполняется только если:
    - initial_service_account.enabled = True в конфигурации
    - Service Account с именем initial_service_account.name не существует

    Args:
        settings: Настройки приложения
        db: Async database session

    Note:
        Service Account используется для OAuth 2.0 Client Credentials flow
        для machine-to-machine аутентификации.

    Examples:
        >>> async with get_db_session() as db:
        ...     await create_initial_service_account(settings, db)
    """
    # Проверка что initial service account создание включено
    if not settings.initial_service_account.enabled:
        logger.info("Initial service account creation disabled in configuration")
        return

    try:
        # Проверка существования Service Account по имени
        result = await db.execute(
            select(ServiceAccount).where(
                ServiceAccount.name == settings.initial_service_account.name
            )
        )
        existing_sa = result.scalars().first()

        if existing_sa:
            logger.debug(
                f"Service Account '{settings.initial_service_account.name}' already exists, skipping",
                extra={
                    "service_account_id": str(existing_sa.id),
                    "client_id": existing_sa.client_id
                }
            )
            return

        # Логирование начала создания
        logger.info(
            f"Creating initial Service Account: {settings.initial_service_account.name}",
            extra={
                "account_name": settings.initial_service_account.name,
                "account_role": settings.initial_service_account.role
            }
        )

        # Определить client_secret (использовать заданный или автогенерировать)
        service = ServiceAccountService()

        if settings.initial_service_account.password:
            # Использовать заданный пароль
            client_secret = settings.initial_service_account.password
            logger.info("Using provided INITIAL_ACCOUNT_PASSWORD for Service Account")
        else:
            # Автогенерация с использованием PasswordGenerator
            from app.core.password_policy import PasswordGenerator, PasswordPolicy

            policy = PasswordPolicy(min_length=settings.password.min_length)
            generator = PasswordGenerator(policy)
            client_secret = generator.generate()

            logger.info("Auto-generated INITIAL_ACCOUNT_PASSWORD for Service Account")

        # Создать Service Account через сервис (автогенерация client_id и хеширование)
        try:
            # Парсинг роли из строки в enum
            role_enum = ServiceAccountRole[settings.initial_service_account.role.upper()]
        except KeyError:
            logger.error(
                f"Invalid role '{settings.initial_service_account.role}'. Using default 'ADMIN'",
                extra={"provided_role": settings.initial_service_account.role}
            )
            role_enum = ServiceAccountRole.ADMIN

        # Генерация client_id
        client_id = ServiceAccount.generate_client_id(
            settings.initial_service_account.name,
            environment="prod"
        )

        # Хеширование client_secret
        client_secret_hash = service.hash_secret(client_secret)

        # Расчет срока истечения secret (90 дней)
        secret_expires_at = ServiceAccount.calculate_secret_expiry(days=90)

        # Создание Service Account объекта
        service_account = ServiceAccount(
            name=settings.initial_service_account.name,
            description="System initial service account (auto-created at startup)",
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            secret_history=[],  # Пустая история при создании
            role=role_enum,
            status=ServiceAccountStatus.ACTIVE,
            is_system=True,  # Защита от удаления через API
            rate_limit=1000,  # Повышенный лимит для системного аккаунта
            secret_expires_at=secret_expires_at
        )

        db.add(service_account)
        await db.commit()
        await db.refresh(service_account)

        # КРИТИЧЕСКИ ВАЖНО: Логирование credentials для администратора
        # Plain text secret логируется ТОЛЬКО при создании (один раз)
        logger.warning(
            "SECURITY AUDIT: Initial Service Account created. "
            "IMPORTANT: Save these credentials securely - they will NOT be shown again!",
            extra={
                "event": "initial_service_account_created",
                "service_account_id": str(service_account.id),
                "account_name": service_account.name,
                "client_id": service_account.client_id,
                "client_secret": client_secret,  # Plain text - ТОЛЬКО при создании!
                "account_role": service_account.role.value,
                "rate_limit": service_account.rate_limit,
                "secret_expires_at": service_account.secret_expires_at.isoformat(),
                "security_risk": "critical"
            }
        )

        logger.info(
            "✅ Initial Service Account created successfully",
            extra={
                "service_account_id": str(service_account.id),
                "account_name": service_account.name,
                "client_id": service_account.client_id,
                "account_role": service_account.role.value
            }
        )

    except Exception as e:
        logger.error(
            f"Failed to create initial Service Account: {e}",
            exc_info=True,
            extra={"error": str(e)}
        )
        await db.rollback()
        raise
