"""
JWT Key Management endpoints.
Мониторинг и управление JWT key rotation.
"""

from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_sync_session
from app.core.config import settings
from app.core.scheduler import get_scheduler_status
from app.schemas.jwt_key import (
    JWTKeyRotationStatus,
    JWTKeyInfo,
    ActiveKeysResponse,
    RotationTriggerRequest,
    RotationTriggerResponse,
    RotationHistoryResponse,
    RotationHistoryEntry
)
from app.models.jwt_key import JWTKey
from app.services.jwt_key_rotation_service import JWTKeyRotationService
from app.api.dependencies.admin_auth import require_role
from app.models.admin_user import AdminRole

router = APIRouter()


@router.get(
    "/status",
    response_model=JWTKeyRotationStatus,
    summary="Получить статус JWT key rotation"
)
async def get_rotation_status(
    session: Session = Depends(get_sync_session),
    current_admin_user = Depends(require_role(AdminRole.ADMIN))
):
    """
    Получение текущего статуса JWT key rotation.

    Требует роль ADMIN.

    Возвращает:
    - Статус автоматической ротации
    - Количество активных ключей
    - Информацию о последнем ключе
    - Время следующей ротации
    - Флаг выполнения ротации
    """
    try:
        # Получаем статус ротации
        rotation_service = JWTKeyRotationService()
        rotation_status = rotation_service.get_rotation_status(session)

        # Получаем последний активный ключ
        latest_key = JWTKey.get_latest_active_key(session)
        latest_key_info = None
        if latest_key:
            latest_key_info = JWTKeyInfo.model_validate(latest_key)

        # Получаем статус scheduler
        scheduler_status = get_scheduler_status()
        next_rotation_at = None
        if scheduler_status.get("running") and scheduler_status.get("jobs"):
            # Ищем JWT rotation job
            for job in scheduler_status["jobs"]:
                if job["id"] == "jwt_key_rotation":
                    next_rotation_at = job.get("next_run_time")
                    break

        return JWTKeyRotationStatus(
            rotation_enabled=settings.scheduler.jwt_rotation_enabled,
            rotation_interval_hours=settings.scheduler.jwt_rotation_interval_hours,
            active_keys_count=rotation_status["active_keys_count"],
            latest_key=latest_key_info,
            next_rotation_at=next_rotation_at,
            last_rotation_at=rotation_status.get("last_rotation_at"),
            rotation_in_progress=rotation_status.get("rotation_in_progress", False)
        )

    finally:
        session.close()


@router.get(
    "/active",
    response_model=ActiveKeysResponse,
    summary="Получить список активных JWT ключей"
)
async def get_active_keys(
    session: Session = Depends(get_sync_session),
    current_admin_user = Depends(require_role(AdminRole.ADMIN))
):
    """
    Получение списка всех активных JWT ключей.

    Требует роль ADMIN.

    Возвращает список ключей с:
    - UUID версии
    - Алгоритмом шифрования
    - Временем создания и истечения
    - Статусом активности
    """
    try:
        active_keys = JWTKey.get_active_keys(session)

        keys_info = [JWTKeyInfo.model_validate(key) for key in active_keys]

        return ActiveKeysResponse(
            total=len(keys_info),
            keys=keys_info
        )

    finally:
        session.close()


@router.post(
    "/rotate",
    response_model=RotationTriggerResponse,
    summary="Ручная ротация JWT ключей"
)
async def trigger_rotation(
    request: RotationTriggerRequest,
    session: Session = Depends(get_sync_session),
    current_admin_user = Depends(require_role(AdminRole.ADMIN))
):
    """
    Ручной запуск ротации JWT ключей.

    Требует роль ADMIN.

    **Параметры:**
    - `force`: Принудительная ротация (игнорирует недавние ротации)

    **Процесс:**
    1. Деактивация истекших ключей
    2. Создание нового ключа с 25-hour validity
    3. Commit изменений

    **Security:**
    - Distributed locking через Redis (60s timeout)
    - Максимум 3 retry попытки
    - Atomic операции через WAL
    """
    try:
        rotation_service = JWTKeyRotationService()

        # Проверяем нужна ли ротация (если не force)
        if not request.force:
            needs_rotation = rotation_service.check_rotation_needed(session)
            if not needs_rotation:
                return RotationTriggerResponse(
                    success=False,
                    message="Rotation not needed. Use force=true to override.",
                )

        # Выполняем ротацию
        success = rotation_service.rotate_keys(session)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to rotate keys. Check logs for details."
            )

        # Получаем информацию о новом ключе
        latest_key = JWTKey.get_latest_active_key(session)
        new_key_version = latest_key.version if latest_key else None

        # Подсчитываем деактивированные ключи
        all_keys = session.query(JWTKey).all()
        deactivated_count = sum(1 for key in all_keys if not key.is_active)

        return RotationTriggerResponse(
            success=True,
            message="JWT keys rotated successfully",
            new_key_version=new_key_version,
            deactivated_keys=deactivated_count
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rotation failed: {str(e)}"
        )

    finally:
        session.close()


@router.get(
    "/history",
    response_model=RotationHistoryResponse,
    summary="Получить историю ротаций JWT ключей"
)
async def get_rotation_history(
    limit: int = 50,
    session: Session = Depends(get_sync_session),
    current_admin_user = Depends(require_role(AdminRole.ADMIN))
):
    """
    Получение истории ротаций JWT ключей.

    Требует роль ADMIN.

    **Параметры:**
    - `limit`: Максимальное количество записей (default: 50, max: 100)

    **Возвращает:**
    - Список всех ключей (активных и деактивированных)
    - Информацию о самом старом активном ключе
    - Информацию о самом новом ключе
    """
    try:
        # Ограничиваем limit
        if limit > 100:
            limit = 100

        # Получаем все ключи, отсортированные по дате создания (новые первыми)
        all_keys = session.query(JWTKey).order_by(
            JWTKey.created_at.desc()
        ).limit(limit).all()

        entries = [
            RotationHistoryEntry(
                key_version=key.version,
                created_at=key.created_at,
                expires_at=key.expires_at,
                is_active=key.is_active,
                rotation_count=key.rotation_count
            )
            for key in all_keys
        ]

        # Находим самый старый активный ключ
        active_keys = [key for key in all_keys if key.is_active]
        oldest_active_key = None
        if active_keys:
            oldest_active = min(active_keys, key=lambda k: k.created_at)
            oldest_active_key = oldest_active.created_at

        # Находим самый новый ключ
        newest_key = None
        if all_keys:
            newest_key = all_keys[0].created_at

        return RotationHistoryResponse(
            total=len(entries),
            entries=entries,
            oldest_active_key=oldest_active_key,
            newest_key=newest_key
        )

    finally:
        session.close()
