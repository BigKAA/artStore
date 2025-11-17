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
from app.models.user import User, UserRole, UserStatus
from app.models.admin_user import AdminUser, AdminRole
from app.services.auth_service import AuthService
from app.services.admin_auth_service import AdminAuthService

logger = logging.getLogger(__name__)


async def create_initial_admin(settings: Settings, db: AsyncSession) -> None:
    """
    Создание начального администратора при первом запуске.

    Выполняется только если:
    - initial_admin.enabled = True в конфигурации
    - В базе данных нет пользователей

    Args:
        settings: Настройки приложения
        db: Async database session

    Примеры:
        >>> async with get_db_session() as db:
        ...     await create_initial_admin(settings, db)
    """
    # Проверка что initial admin создание включено
    if not settings.initial_admin.enabled:
        logger.info("Initial admin creation disabled in configuration")
        return

    try:
        # Проверка существования пользователей в БД
        result = await db.execute(select(func.count()).select_from(User))
        user_count = result.scalar()

        if user_count > 0:
            logger.debug(f"Users already exist in database (count: {user_count}), skipping initial admin creation")
            return

        # Создание initial admin пользователя
        logger.info(
            "No users found in database, creating initial administrator",
            extra={
                "username": settings.initial_admin.username,
                "email": settings.initial_admin.email
            }
        )

        # Хеширование пароля
        password_hash = AuthService.hash_password(settings.initial_admin.password)

        # Создание User объекта
        admin_user = User(
            username=settings.initial_admin.username,
            hashed_password=password_hash,
            email=settings.initial_admin.email,
            first_name=settings.initial_admin.firstname,
            last_name=settings.initial_admin.lastname,
            role=UserRole.ADMIN,  # Административная роль
            status=UserStatus.ACTIVE,
            is_system=True  # System admin не может быть удален
        )

        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)

        logger.info(
            "Initial administrator created successfully",
            extra={
                "user_id": admin_user.id,
                "username": admin_user.username,
                "email": admin_user.email,
                "role": admin_user.role
            }
        )

        # Audit log для безопасности
        logger.warning(
            "SECURITY AUDIT: Initial administrator account was automatically created. "
            "Please change the password immediately through the API or admin interface.",
            extra={
                "event": "initial_admin_created",
                "user_id": admin_user.id,
                "username": admin_user.username
            }
        )

    except Exception as e:
        logger.error(
            f"Failed to create initial administrator: {e}",
            exc_info=True,
            extra={"error": str(e)}
        )
        await db.rollback()
        raise


async def create_initial_admin_user(settings: Settings, db: AsyncSession) -> None:
    """
    Создание начального Admin User для Admin UI при первом запуске.

    Выполняется только если:
    - В базе данных нет admin_users
    - Конфигурация позволяет создание

    Args:
        settings: Настройки приложения
        db: Async database session

    Note:
        Admin User отличается от legacy User (LDAP).
        Admin User используется для аутентификации в Admin UI через login/password.

    Examples:
        >>> async with get_db_session() as db:
        ...     await create_initial_admin_user(settings, db)
    """
    try:
        # Проверка существования admin users в БД
        result = await db.execute(select(func.count()).select_from(AdminUser))
        admin_count = result.scalar()

        if admin_count > 0:
            logger.debug(f"Admin users already exist in database (count: {admin_count}), skipping initial admin user creation")
            return

        # Создание initial admin user
        logger.info("No admin users found in database, creating initial admin user for Admin UI")

        # Хеширование пароля
        admin_auth_service = AdminAuthService()
        password_hash = admin_auth_service.hash_password("admin123")  # TODO: Get from env variable

        # Создание AdminUser объекта
        initial_admin = AdminUser(
            username="admin",
            email="admin@artstore.local",
            password_hash=password_hash,
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
