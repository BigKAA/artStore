"""
Admin User Management Service для CRUD операций с администраторами.

Используется для управления администраторами через Admin UI.
Требует роль SUPER_ADMIN для большинства операций.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple
import logging
import uuid

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext

from app.models.admin_user import AdminUser, AdminRole
from app.schemas.admin_user import (
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    AdminUserPasswordResetRequest,
    AdminUserResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserDeleteResponse,
    AdminUserPasswordResetResponse
)
from app.core.password_policy import PasswordPolicy, PasswordValidator, PasswordGenerator
from app.services.audit_service import AuditService
from app.core.database import get_sync_session

logger = logging.getLogger(__name__)

# Bcrypt context для хеширования паролей (work factor 12)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AdminUserServiceError(Exception):
    """Базовое исключение для ошибок Admin User Service."""
    pass


class AdminUserNotFoundError(AdminUserServiceError):
    """Администратор не найден."""
    pass


class AdminUserAlreadyExistsError(AdminUserServiceError):
    """Администратор с таким username или email уже существует."""
    pass


class SystemAdminProtectedError(AdminUserServiceError):
    """Системный администратор защищен от удаления/модификации."""
    pass


class InsufficientPermissionsError(AdminUserServiceError):
    """Недостаточно прав для выполнения операции."""
    pass


class AdminUserService:
    """
    Сервис для CRUD операций с администраторами Admin UI.

    Функции:
    - Создание нового администратора (SUPER_ADMIN only)
    - Получение списка администраторов (с пагинацией и фильтрацией)
    - Получение информации об администраторе
    - Обновление администратора (SUPER_ADMIN only)
    - Удаление администратора (SUPER_ADMIN only, кроме системных)
    - Сброс пароля администратора (SUPER_ADMIN only)
    """

    def __init__(self):
        """Инициализация сервиса управления администраторами."""
        self.password_policy = PasswordPolicy(
            min_length=8,
            require_uppercase=True,
            require_lowercase=True,
            require_digits=True,
            require_special=False,
            max_age_days=90,
            history_size=5
        )
        self.password_validator = PasswordValidator(self.password_policy)
        self.password_generator = PasswordGenerator(self.password_policy)

        # Note: AuditService использование будет добавлено при необходимости
        # через dependency injection в endpoints

    async def create_admin_user(
        self,
        db: AsyncSession,
        request: AdminUserCreateRequest,
        created_by: AdminUser
    ) -> AdminUserResponse:
        """
        Создать нового администратора.

        Args:
            db: Async database session
            request: Данные нового администратора
            created_by: Администратор, создающий нового пользователя (должен быть SUPER_ADMIN)

        Returns:
            AdminUserResponse с данными созданного администратора

        Raises:
            InsufficientPermissionsError: Если created_by не SUPER_ADMIN
            AdminUserAlreadyExistsError: Если username или email уже существуют
        """
        # Проверка прав доступа
        if created_by.role != AdminRole.SUPER_ADMIN:
            logger.warning(
                f"Admin user {created_by.username} (role={created_by.role}) attempted to create admin user",
                extra={"admin_user_id": str(created_by.id)}
            )
            raise InsufficientPermissionsError("Only SUPER_ADMIN can create admin users")

        # Валидация пароля
        is_valid, error_message = self.password_validator.validate(request.password)
        if not is_valid:
            raise AdminUserServiceError(f"Password validation failed: {error_message}")

        # Хеширование пароля
        password_hash = pwd_context.hash(request.password)

        # Создание нового администратора
        new_admin = AdminUser(
            id=uuid.uuid4(),
            username=request.username.lower(),  # Приводим к lowercase
            email=request.email,
            password_hash=password_hash,
            role=request.role,
            enabled=request.enabled,
            is_system=False,  # Обычные администраторы не системные
            password_changed_at=datetime.now(timezone.utc),
            password_history=[password_hash],  # Первый пароль в истории
            login_attempts=0,
            locked_until=None,
            last_login_at=None
        )

        try:
            db.add(new_admin)
            await db.commit()
            await db.refresh(new_admin)

            logger.info(
                f"Admin user created: {new_admin.username} (role={new_admin.role}) by {created_by.username}",
                extra={
                    "admin_user_id": str(new_admin.id),
                    "created_by": str(created_by.id),
                    "username": new_admin.username,
                    "role": new_admin.role.value
                }
            )

            # Audit log
            with get_sync_session() as sync_session:
                audit = AuditService(sync_session)
                audit.log_sensitive_operation(
                    admin_user_id=created_by.id,
                    action="admin_user_created",
                    resource_type="admin_user",
                    resource_id=str(new_admin.id),
                    details={
                        "username": new_admin.username,
                        "role": new_admin.role.value,
                        "created_by": created_by.username
                    }
                )

            return AdminUserResponse.model_validate(new_admin)

        except IntegrityError as e:
            await db.rollback()
            error_msg = str(e.orig)

            if "username" in error_msg:
                raise AdminUserAlreadyExistsError(f"Username '{request.username}' already exists")
            elif "email" in error_msg:
                raise AdminUserAlreadyExistsError(f"Email '{request.email}' already exists")
            else:
                raise AdminUserServiceError(f"Database integrity error: {error_msg}")

    async def get_admin_user_list(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 10,
        role_filter: Optional[AdminRole] = None,
        enabled_filter: Optional[bool] = None,
        search_query: Optional[str] = None
    ) -> AdminUserListResponse:
        """
        Получить список администраторов с пагинацией и фильтрацией.

        Args:
            db: Async database session
            page: Номер страницы (starting from 1)
            page_size: Размер страницы (количество элементов)
            role_filter: Фильтр по роли (опционально)
            enabled_filter: Фильтр по статусу (опционально)
            search_query: Поиск по username или email (опционально)

        Returns:
            AdminUserListResponse с списком администраторов и метаданными пагинации
        """
        # Построение базового запроса
        query = select(AdminUser)

        # Применение фильтров
        if role_filter is not None:
            query = query.where(AdminUser.role == role_filter)

        if enabled_filter is not None:
            query = query.where(AdminUser.enabled == enabled_filter)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.where(
                or_(
                    AdminUser.username.ilike(search_pattern),
                    AdminUser.email.ilike(search_pattern)
                )
            )

        # Подсчет общего количества
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # Вычисление offset и применение пагинации
        offset = (page - 1) * page_size
        query = query.order_by(AdminUser.created_at.desc()).offset(offset).limit(page_size)

        # Получение данных
        result = await db.execute(query)
        admin_users = result.scalars().all()

        # Формирование ответа
        items = [AdminUserListItem.model_validate(user) for user in admin_users]
        total_pages = (total + page_size - 1) // page_size  # Округление вверх

        return AdminUserListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    async def get_admin_user_by_id(
        self,
        db: AsyncSession,
        admin_id: uuid.UUID
    ) -> AdminUserResponse:
        """
        Получить информацию об администраторе по ID.

        Args:
            db: Async database session
            admin_id: UUID администратора

        Returns:
            AdminUserResponse с данными администратора

        Raises:
            AdminUserNotFoundError: Если администратор не найден
        """
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == admin_id)
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            raise AdminUserNotFoundError(f"Admin user with id {admin_id} not found")

        return AdminUserResponse.model_validate(admin_user)

    async def update_admin_user(
        self,
        db: AsyncSession,
        admin_id: uuid.UUID,
        request: AdminUserUpdateRequest,
        updated_by: AdminUser
    ) -> AdminUserResponse:
        """
        Обновить администратора.

        Args:
            db: Async database session
            admin_id: UUID администратора для обновления
            request: Данные для обновления
            updated_by: Администратор, выполняющий обновление (должен быть SUPER_ADMIN)

        Returns:
            AdminUserResponse с обновленными данными

        Raises:
            InsufficientPermissionsError: Если updated_by не SUPER_ADMIN
            AdminUserNotFoundError: Если администратор не найден
            SystemAdminProtectedError: Если попытка модификации системного администратора
            AdminUserAlreadyExistsError: Если email уже существует
        """
        # Проверка прав доступа
        if updated_by.role != AdminRole.SUPER_ADMIN:
            logger.warning(
                f"Admin user {updated_by.username} (role={updated_by.role}) attempted to update admin user",
                extra={"admin_user_id": str(updated_by.id)}
            )
            raise InsufficientPermissionsError("Only SUPER_ADMIN can update admin users")

        # Получение администратора
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == admin_id)
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            raise AdminUserNotFoundError(f"Admin user with id {admin_id} not found")

        # Защита системного администратора
        if admin_user.is_system:
            raise SystemAdminProtectedError("System admin user cannot be modified")

        # Применение обновлений
        update_details = {}

        if request.email is not None and request.email != admin_user.email:
            admin_user.email = request.email
            update_details["email"] = request.email

        if request.role is not None and request.role != admin_user.role:
            admin_user.role = request.role
            update_details["role"] = request.role.value

        if request.enabled is not None and request.enabled != admin_user.enabled:
            admin_user.enabled = request.enabled
            update_details["enabled"] = request.enabled

            # Сброс блокировки и попыток при включении аккаунта
            if request.enabled:
                admin_user.locked_until = None
                admin_user.login_attempts = 0

        if not update_details:
            # Нет изменений
            return AdminUserResponse.model_validate(admin_user)

        admin_user.updated_at = datetime.now(timezone.utc)

        try:
            await db.commit()
            await db.refresh(admin_user)

            logger.info(
                f"Admin user updated: {admin_user.username} by {updated_by.username}",
                extra={
                    "admin_user_id": str(admin_user.id),
                    "updated_by": str(updated_by.id),
                    "changes": update_details
                }
            )

            # Audit log
            with get_sync_session() as sync_session:
                audit = AuditService(sync_session)
                audit.log_sensitive_operation(
                    admin_user_id=updated_by.id,
                    action="admin_user_updated",
                    resource_type="admin_user",
                    resource_id=str(admin_user.id),
                    details={
                        "username": admin_user.username,
                        "updated_by": updated_by.username,
                        "changes": update_details
                    }
                )

            return AdminUserResponse.model_validate(admin_user)

        except IntegrityError as e:
            await db.rollback()
            error_msg = str(e.orig)

            if "email" in error_msg:
                raise AdminUserAlreadyExistsError(f"Email '{request.email}' already exists")
            else:
                raise AdminUserServiceError(f"Database integrity error: {error_msg}")

    async def delete_admin_user(
        self,
        db: AsyncSession,
        admin_id: uuid.UUID,
        deleted_by: AdminUser
    ) -> AdminUserDeleteResponse:
        """
        Удалить администратора.

        Args:
            db: Async database session
            admin_id: UUID администратора для удаления
            deleted_by: Администратор, выполняющий удаление (должен быть SUPER_ADMIN)

        Returns:
            AdminUserDeleteResponse с подтверждением удаления

        Raises:
            InsufficientPermissionsError: Если deleted_by не SUPER_ADMIN
            AdminUserNotFoundError: Если администратор не найден
            SystemAdminProtectedError: Если попытка удаления системного администратора
        """
        # Проверка прав доступа
        if deleted_by.role != AdminRole.SUPER_ADMIN:
            logger.warning(
                f"Admin user {deleted_by.username} (role={deleted_by.role}) attempted to delete admin user",
                extra={"admin_user_id": str(deleted_by.id)}
            )
            raise InsufficientPermissionsError("Only SUPER_ADMIN can delete admin users")

        # Получение администратора
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == admin_id)
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            raise AdminUserNotFoundError(f"Admin user with id {admin_id} not found")

        # Защита системного администратора
        if admin_user.is_system:
            raise SystemAdminProtectedError("System admin user cannot be deleted")

        # Запрет удаления самого себя
        if admin_user.id == deleted_by.id:
            raise AdminUserServiceError("Cannot delete your own admin account")

        # Удаление
        username = admin_user.username
        await db.delete(admin_user)
        await db.commit()

        logger.info(
            f"Admin user deleted: {username} by {deleted_by.username}",
            extra={
                "admin_user_id": str(admin_id),
                "deleted_by": str(deleted_by.id),
                "username": username
            }
        )

        # Audit log
        with get_sync_session() as sync_session:
            audit = AuditService(sync_session)
            audit.log_sensitive_operation(
                admin_user_id=deleted_by.id,
                action="admin_user_deleted",
                resource_type="admin_user",
                resource_id=str(admin_id),
                details={
                    "username": username,
                    "deleted_by": deleted_by.username
                }
            )

        return AdminUserDeleteResponse(
            success=True,
            message="Admin user deleted successfully",
            deleted_id=admin_id
        )

    async def reset_admin_password(
        self,
        db: AsyncSession,
        admin_id: uuid.UUID,
        request: AdminUserPasswordResetRequest,
        reset_by: AdminUser
    ) -> AdminUserPasswordResetResponse:
        """
        Сбросить пароль администратора (SUPER_ADMIN only).

        Args:
            db: Async database session
            admin_id: UUID администратора
            request: Новый пароль
            reset_by: Администратор, выполняющий сброс (должен быть SUPER_ADMIN)

        Returns:
            AdminUserPasswordResetResponse с подтверждением сброса

        Raises:
            InsufficientPermissionsError: Если reset_by не SUPER_ADMIN
            AdminUserNotFoundError: Если администратор не найден
            SystemAdminProtectedError: Если попытка сброса пароля системного администратора
        """
        # Проверка прав доступа
        if reset_by.role != AdminRole.SUPER_ADMIN:
            logger.warning(
                f"Admin user {reset_by.username} (role={reset_by.role}) attempted to reset password",
                extra={"admin_user_id": str(reset_by.id)}
            )
            raise InsufficientPermissionsError("Only SUPER_ADMIN can reset admin passwords")

        # Получение администратора
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == admin_id)
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            raise AdminUserNotFoundError(f"Admin user with id {admin_id} not found")

        # Защита системного администратора
        if admin_user.is_system:
            raise SystemAdminProtectedError("System admin password cannot be reset by other admins")

        # Валидация нового пароля
        is_valid, error_message = self.password_validator.validate(request.new_password)
        if not is_valid:
            raise AdminUserServiceError(f"Password validation failed: {error_message}")

        # Хеширование нового пароля
        new_password_hash = pwd_context.hash(request.new_password)

        # Обновление пароля
        admin_user.password_hash = new_password_hash
        admin_user.password_changed_at = datetime.now(timezone.utc)

        # Обновление истории паролей (максимум 5)
        if admin_user.password_history is None:
            admin_user.password_history = []
        admin_user.password_history = ([new_password_hash] + admin_user.password_history)[:5]

        # Сброс блокировки и попыток
        admin_user.locked_until = None
        admin_user.login_attempts = 0

        admin_user.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(admin_user)

        logger.info(
            f"Admin user password reset: {admin_user.username} by {reset_by.username}",
            extra={
                "admin_user_id": str(admin_user.id),
                "reset_by": str(reset_by.id),
                "username": admin_user.username
            }
        )

        # Audit log
        with get_sync_session() as sync_session:
            audit = AuditService(sync_session)
            audit.log_sensitive_operation(
                admin_user_id=reset_by.id,
                action="admin_password_reset",
                resource_type="admin_user",
                resource_id=str(admin_user.id),
                details={
                    "username": admin_user.username,
                    "reset_by": reset_by.username
                }
            )

        return AdminUserPasswordResetResponse(
            success=True,
            message="Password reset successfully",
            password_changed_at=admin_user.password_changed_at
        )
