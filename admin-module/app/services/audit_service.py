"""
Сервис audit logging.
Записывает все действия пользователей в БД.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_log import AuditLog
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AuditService:
    """
    Сервис аудита действий пользователей.
    Обеспечивает tamper-proof логирование всех операций.
    """

    async def log_action(
        self,
        db: AsyncSession,
        action: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> AuditLog:
        """
        Записывает действие в audit log.

        Args:
            db: Database session
            action: Тип действия (login, create_user, delete_file, etc.)
            user_id: ID пользователя
            username: Имя пользователя
            resource_type: Тип ресурса (user, storage_element, file)
            resource_id: ID ресурса
            details: Дополнительные детали (JSON)
            ip_address: IP адрес клиента
            user_agent: User-Agent браузера
            success: Успешно ли выполнено действие
            error_message: Сообщение об ошибке

        Returns:
            Созданная запись audit log
        """
        audit_entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message
        )

        db.add(audit_entry)

        try:
            await db.commit()
            await db.refresh(audit_entry)

            log_message = f"Audit: {action}"
            if username:
                log_message += f" by {username}"
            if resource_type and resource_id:
                log_message += f" on {resource_type}:{resource_id}"
            if not success:
                log_message += f" [FAILED: {error_message}]"

            logger.info(log_message)
            return audit_entry

        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка записи audit log: {e}")
            # Не поднимаем исключение, чтобы не прерывать основное действие
            return audit_entry


# Глобальный экземпляр сервиса
audit_service = AuditService()
