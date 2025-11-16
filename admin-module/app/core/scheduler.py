"""
APScheduler background задачи для Admin Module.

Функции:
- Автоматическая ротация JWT ключей каждые 24 часа
- Background job scheduling с error handling
- Graceful shutdown при остановке приложения
"""

import logging
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from pytz import timezone as pytz_timezone

from app.core.config import settings
from app.core.database import get_sync_session
from app.services.jwt_key_rotation_service import get_rotation_service

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def jwt_rotation_job() -> None:
    """
    Background задача для ротации JWT ключей.

    Выполняется периодически согласно настройкам scheduler.jwt_rotation_interval_hours.
    Использует distributed locking через Redis для cluster-safe операций.

    Процесс:
    1. Создание database session
    2. Проверка необходимости ротации
    3. Выполнение ротации с distributed locking
    4. Cleanup session

    Note:
        Эта функция должна быть максимально устойчивой к ошибкам,
        так как она выполняется автоматически без вмешательства пользователя.
    """
    logger.info("JWT key rotation job started")

    session = None
    try:
        # Создаем синхронную database session
        session = next(get_sync_session())

        # Получаем rotation service
        rotation_service = get_rotation_service()

        # Проверяем необходимость ротации
        if not rotation_service.check_rotation_needed(session):
            logger.info("JWT key rotation not needed, skipping")
            return

        # Выполняем ротацию с distributed locking
        success = rotation_service.rotate_keys(session)

        if success:
            logger.info("JWT key rotation job completed successfully")
        else:
            logger.error("JWT key rotation job failed - check logs for details")

    except Exception as e:
        logger.error(f"JWT key rotation job failed with exception: {e}", exc_info=True)

    finally:
        # Закрываем session
        if session:
            session.close()


def job_listener(event) -> None:
    """
    Listener для событий APScheduler.

    Args:
        event: Событие от APScheduler (EVENT_JOB_EXECUTED или EVENT_JOB_ERROR)

    Логирует выполнение и ошибки background задач для мониторинга.
    """
    if event.exception:
        logger.error(
            f"Job {event.job_id} raised exception: {event.exception}",
            extra={
                "job_id": event.job_id,
                "scheduled_run_time": event.scheduled_run_time.isoformat() if event.scheduled_run_time else None
            }
        )
    else:
        logger.debug(
            f"Job {event.job_id} executed successfully",
            extra={
                "job_id": event.job_id,
                "scheduled_run_time": event.scheduled_run_time.isoformat() if event.scheduled_run_time else None
            }
        )


def init_scheduler() -> Optional[BackgroundScheduler]:
    """
    Инициализация APScheduler с background задачами.

    Returns:
        Optional[BackgroundScheduler]: Scheduler instance или None если disabled

    Raises:
        Exception: При ошибке инициализации scheduler

    Example:
        @app.on_event("startup")
        async def startup_event():
            init_scheduler()
    """
    global _scheduler

    if not settings.scheduler.enabled:
        logger.info("Scheduler disabled in configuration")
        return None

    if _scheduler is not None:
        logger.warning("Scheduler already initialized")
        return _scheduler

    try:
        # Создаем scheduler с timezone из конфигурации
        tz = pytz_timezone(settings.scheduler.timezone)
        _scheduler = BackgroundScheduler(timezone=tz)

        # Добавляем listener для событий
        _scheduler.add_listener(
            job_listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        # JWT Key Rotation job
        if settings.scheduler.jwt_rotation_enabled:
            _scheduler.add_job(
                func=jwt_rotation_job,
                trigger=IntervalTrigger(
                    hours=settings.scheduler.jwt_rotation_interval_hours,
                    timezone=tz
                ),
                id="jwt_key_rotation",
                name="JWT Key Rotation",
                replace_existing=True,
                max_instances=1,  # Только одна инстанция job может выполняться одновременно
                coalesce=True,  # Если пропущено несколько запусков, выполнить только один
                misfire_grace_time=3600  # 1 час grace period для missed jobs
            )

            logger.info(
                f"JWT key rotation job scheduled: "
                f"interval={settings.scheduler.jwt_rotation_interval_hours}h, "
                f"timezone={settings.scheduler.timezone}"
            )

        # Запускаем scheduler
        _scheduler.start()
        logger.info("APScheduler started successfully")

        return _scheduler

    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {e}", exc_info=True)
        raise


def shutdown_scheduler() -> None:
    """
    Graceful shutdown scheduler при остановке приложения.

    Ожидает завершения всех running jobs (до 30 секунд).

    Example:
        @app.on_event("shutdown")
        async def shutdown_event():
            shutdown_scheduler()
    """
    global _scheduler

    if _scheduler is None:
        return

    try:
        logger.info("Shutting down scheduler...")

        # Ожидаем завершения running jobs (максимум 30 секунд)
        _scheduler.shutdown(wait=True)

        _scheduler = None
        logger.info("Scheduler shut down successfully")

    except Exception as e:
        logger.error(f"Error during scheduler shutdown: {e}", exc_info=True)


def get_scheduler() -> Optional[BackgroundScheduler]:
    """
    Получение текущего scheduler instance.

    Returns:
        Optional[BackgroundScheduler]: Scheduler instance или None если не инициализирован

    Example:
        scheduler = get_scheduler()
        if scheduler:
            jobs = scheduler.get_jobs()
            for job in jobs:
                print(f"Job: {job.name}, Next run: {job.next_run_time}")
    """
    return _scheduler


def get_scheduler_status() -> dict:
    """
    Получение статуса scheduler и его jobs.

    Returns:
        dict: Статус scheduler с информацией о jobs

    Example:
        {
            "enabled": true,
            "running": true,
            "jobs": [
                {
                    "id": "jwt_key_rotation",
                    "name": "JWT Key Rotation",
                    "next_run_time": "2025-11-17T16:00:00Z",
                    "pending": false
                }
            ]
        }
    """
    if _scheduler is None:
        return {
            "enabled": settings.scheduler.enabled,
            "running": False,
            "jobs": []
        }

    try:
        jobs_info = []
        for job in _scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "pending": job.pending
            })

        return {
            "enabled": settings.scheduler.enabled,
            "running": _scheduler.running,
            "jobs": jobs_info
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        return {
            "enabled": settings.scheduler.enabled,
            "running": False,
            "error": str(e)
        }
