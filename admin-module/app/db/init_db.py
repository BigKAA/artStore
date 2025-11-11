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
from app.services.auth_service import AuthService

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
