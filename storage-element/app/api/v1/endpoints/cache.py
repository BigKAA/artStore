"""
Cache Management API Endpoints.

Endpoints для управления синхронизацией PostgreSQL кеша с attr.json файлами.

PHASE 5: API Endpoints (Hybrid Cache Synchronization)

Endpoints:
- POST /api/v1/cache/rebuild - полная пересборка кеша
- POST /api/v1/cache/rebuild/incremental - инкрементальная пересборка
- GET /api/v1/cache/consistency - проверка консистентности
- POST /api/v1/cache/cleanup-expired - очистка expired entries

Доступ: Только для Service Accounts с ролью ADMIN.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_service_account
from app.services.cache_rebuild_service import (
    CacheRebuildService,
    ConsistencyReport,
    RebuildResult
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/rebuild",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Полная пересборка кеша",
    description="""
    Полная пересборка PostgreSQL кеша из attr.json файлов.

    **Процесс:**
    1. TRUNCATE таблицы cache
    2. Scan всех attr.json файлов из storage
    3. INSERT метаданных в cache

    **Используется:**
    - При обнаружении значительных расхождений (>10%)
    - После восстановления storage из backup
    - При миграции данных

    **Внимание:** Операция может занять длительное время для больших хранилищ.

    **Требования:**
    - Service Account с ролью ADMIN
    - Exclusive lock (блокирует другие cache операции)

    **Timeout:** 30 минут
    """
)
async def rebuild_cache_full(
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_service_account)
) -> dict:
    """
    Полная пересборка кеша из attr.json файлов.

    Args:
        db: Database session
        _auth: Service account authentication (dependency)

    Returns:
        dict: Результат пересборки (статистика, duration, errors)

    Raises:
        HTTPException 503: Если не удалось получить lock (другая операция в процессе)
        HTTPException 500: При ошибках во время rebuild
    """
    logger.info(
        "Full cache rebuild requested",
        extra={
            "requester": _auth.client_id,
            "role": _auth.role
        }
    )

    rebuild_service = CacheRebuildService(db=db)

    try:
        result: RebuildResult = await rebuild_service.rebuild_cache_full()

        logger.info(
            "Full cache rebuild completed successfully",
            extra={
                "duration_seconds": result.duration_seconds,
                "entries_created": result.entries_created,
                "errors": len(result.errors)
            }
        )

        return {
            "status": "success",
            "message": "Cache rebuild completed successfully",
            "result": result.to_dict()
        }

    except RuntimeError as e:
        # Lock acquisition failure
        logger.warning(f"Cannot acquire lock for cache rebuild: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Cache rebuild failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cache rebuild failed: {str(e)}"
        )


@router.post(
    "/rebuild/incremental",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Инкрементальная пересборка кеша",
    description="""
    Инкрементальная пересборка - добавляет только отсутствующие записи.

    **Процесс:**
    1. Получить список file_id из cache
    2. Scan attr.json файлов
    3. INSERT только отсутствующих в cache

    **Используется:**
    - После добавления новых файлов вне штатного процесса
    - Для синхронизации после ручного копирования файлов
    - Менее затратно чем full rebuild

    **НЕ удаляет:** orphan cache entries (записи без attr.json)

    **Требования:**
    - Service Account с ролью ADMIN
    - Exclusive lock

    **Timeout:** 30 минут
    """
)
async def rebuild_cache_incremental(
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_service_account)
) -> dict:
    """
    Инкрементальная пересборка кеша.

    Добавляет в cache только те файлы, для которых есть attr.json,
    но нет записи в PostgreSQL кеше.

    Args:
        db: Database session
        _auth: Service account authentication

    Returns:
        dict: Результат пересборки

    Raises:
        HTTPException 503: Lock acquisition failure
        HTTPException 500: Rebuild error
    """
    logger.info(
        "Incremental cache rebuild requested",
        extra={"requester": _auth.client_id}
    )

    rebuild_service = CacheRebuildService(db=db)

    try:
        result: RebuildResult = await rebuild_service.rebuild_cache_incremental()

        logger.info(
            "Incremental cache rebuild completed",
            extra={
                "duration_seconds": result.duration_seconds,
                "entries_created": result.entries_created
            }
        )

        return {
            "status": "success",
            "message": "Incremental cache rebuild completed",
            "result": result.to_dict()
        }

    except RuntimeError as e:
        logger.warning(f"Cannot acquire lock for incremental rebuild: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Incremental rebuild failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Incremental rebuild failed: {str(e)}"
        )


@router.get(
    "/consistency",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Проверка консистентности кеша",
    description="""
    Проверка консистентности PostgreSQL кеша с attr.json файлами.

    **Dry-run операция** - НЕ изменяет данные, только анализирует.

    **Проверяет:**
    - Orphan cache entries (в cache есть, но нет attr.json)
    - Orphan attr files (attr.json есть, но нет в cache)
    - Expired cache entries (TTL истёк)
    - Процент несоответствий

    **Используется:**
    - Для диагностики проблем синхронизации
    - Перед принятием решения о rebuild
    - В мониторинге для alerting

    **Требования:**
    - Service Account (любая роль может читать)
    - Non-blocking lock (не блокирует lazy rebuild)

    **Timeout:** 10 минут
    """
)
async def check_consistency(
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_service_account)
) -> dict:
    """
    Проверка консистентности кеша (dry-run).

    Args:
        db: Database session
        _auth: Service account authentication

    Returns:
        dict: Отчёт о консистентности

    Raises:
        HTTPException 503: Lock acquisition failure
        HTTPException 500: Check error
    """
    logger.info(
        "Cache consistency check requested",
        extra={"requester": _auth.client_id}
    )

    rebuild_service = CacheRebuildService(db=db)

    try:
        report: ConsistencyReport = await rebuild_service.check_consistency(dry_run=True)

        logger.info(
            "Cache consistency check completed",
            extra={
                "is_consistent": report.is_consistent,
                "inconsistency_percentage": report.inconsistency_percentage,
                "orphan_cache": len(report.orphan_cache_entries),
                "orphan_attr": len(report.orphan_attr_files),
                "expired": len(report.expired_cache_entries)
            }
        )

        return {
            "status": "success",
            "message": "Consistency check completed",
            "report": report.to_dict()
        }

    except RuntimeError as e:
        logger.warning(f"Cannot acquire lock for consistency check: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Consistency check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Consistency check failed: {str(e)}"
        )


@router.post(
    "/cleanup-expired",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Очистка expired cache entries",
    description="""
    Удаление cache entries с истёкшим TTL.

    **Процесс:**
    1. Find entries где cache_updated_at + cache_ttl_hours < now()
    2. DELETE expired entries

    **Используется:**
    - Для освобождения места в cache
    - Background cleanup job (опционально)
    - Lowest priority lock (не блокирует важные операции)

    **Внимание:** Lazy rebuild автоматически обновит эти entries при запросах,
    поэтому cleanup опционален.

    **Требования:**
    - Service Account с ролью ADMIN
    - Background cleanup lock (lowest priority)

    **Timeout:** 5 минут
    """
)
async def cleanup_expired_entries(
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_service_account)
) -> dict:
    """
    Очистка expired cache entries.

    Args:
        db: Database session
        _auth: Service account authentication

    Returns:
        dict: Результат cleanup

    Raises:
        HTTPException 503: Lock acquisition failure
        HTTPException 500: Cleanup error
    """
    logger.info(
        "Expired cache cleanup requested",
        extra={"requester": _auth.client_id}
    )

    rebuild_service = CacheRebuildService(db=db)

    try:
        result: RebuildResult = await rebuild_service.cleanup_expired_entries()

        logger.info(
            "Expired cache cleanup completed",
            extra={
                "entries_deleted": result.entries_deleted,
                "duration_seconds": result.duration_seconds
            }
        )

        return {
            "status": "success",
            "message": "Expired cache cleanup completed",
            "result": result.to_dict()
        }

    except RuntimeError as e:
        logger.warning(f"Cannot acquire lock for cleanup: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Cache cleanup failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cache cleanup failed: {str(e)}"
        )
