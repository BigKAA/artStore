"""
APScheduler background задачи для Admin Module.

Функции:
- Автоматическая ротация JWT ключей каждые 24 часа
- Периодическая публикация конфигурации Storage Elements в Redis
- Периодическая проверка состояния Storage Elements (health check)
- Background job scheduling с error handling
- Graceful shutdown при остановке приложения
"""

import asyncio
import logging
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from pytz import timezone as pytz_timezone

from app.core.config import settings
from app.core.database import get_sync_session, create_standalone_async_session
from app.services.jwt_key_rotation_service import get_rotation_service
from app.services.storage_element_publish_service import storage_element_publish_service
from app.services.storage_sync_service import storage_sync_service
from app.services.garbage_collector_service import GarbageCollectorService

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


def storage_element_publish_job() -> None:
    """
    Background задача для периодической публикации конфигурации Storage Elements в Redis.

    Выполняется периодически согласно настройкам service_discovery.publish_interval_seconds.
    Публикует текущую конфигурацию всех Storage Elements в Redis для Service Discovery.

    Ingester и Query модули подписываются на обновления через Redis Pub/Sub
    и получают актуальную конфигурацию без перезапуска.

    Процесс:
    1. Создание async database session
    2. Получение всех storage elements
    3. Публикация конфигурации в Redis
    4. Cleanup session

    Note:
        Эта функция запускает async код через asyncio.run(),
        так как APScheduler BackgroundScheduler работает синхронно.
    """
    logger.debug("Storage element publish job started")

    async def _publish():
        """Внутренняя async функция для публикации."""
        # Создаем standalone session для нового event loop
        session = await create_standalone_async_session()
        try:
            # Используем standalone метод с собственным Redis client
            subscribers = await storage_element_publish_service.publish_scheduled_standalone(session)
            logger.debug(
                f"Storage element config published to {subscribers} subscribers"
            )
        except Exception as e:
            logger.error(
                f"Storage element publish job failed: {e}",
                exc_info=True
            )
        finally:
            await session.close()

    try:
        # Запускаем async функцию в sync контексте
        asyncio.run(_publish())
    except Exception as e:
        logger.error(f"Storage element publish job failed with exception: {e}", exc_info=True)


def storage_health_check_job() -> None:
    """
    Background задача для периодической проверки состояния Storage Elements.

    Выполняется периодически согласно настройкам scheduler.storage_health_check_interval_seconds.
    Опрашивает /api/v1/info каждого Storage Element и синхронизирует данные в БД.

    Процесс:
    1. Получение всех Storage Elements из БД
    2. Опрос /api/v1/info для каждого элемента
    3. Обновление mode, status, capacity, used_bytes, file_count при изменении
    4. Публикация изменений в Redis для Service Discovery

    Note:
        При изменении режима (mode) Storage Element логируется событие.
        Режим может измениться только если администратор перезапустил
        Storage Element с новой конфигурацией APP_MODE.
    """
    logger.debug("Storage health check job started")

    async def _health_check():
        """Внутренняя async функция для health check."""
        session = await create_standalone_async_session()
        try:
            # Синхронизируем все storage elements (включая offline для обновления статуса)
            results = await storage_sync_service.sync_all_storage_elements(
                session,
                only_online=False  # Проверяем все элементы
            )

            # Подсчитываем статистику
            success_count = sum(1 for r in results if r.success)
            failed_count = len(results) - success_count
            changes_count = sum(len(r.changes) for r in results)

            # Логируем только если есть изменения или ошибки
            if changes_count > 0 or failed_count > 0:
                logger.info(
                    f"Storage health check completed: "
                    f"{success_count} synced, {failed_count} failed, "
                    f"{changes_count} changes detected"
                )
            else:
                logger.debug(
                    f"Storage health check completed: "
                    f"{success_count} synced, no changes"
                )

        except Exception as e:
            logger.error(
                f"Storage health check job failed: {e}",
                exc_info=True
            )
        finally:
            await session.close()

    try:
        asyncio.run(_health_check())
    except Exception as e:
        logger.error(f"Storage health check job failed with exception: {e}", exc_info=True)


def readiness_health_check_job() -> None:
    """
    Background задача для периодической проверки readiness состояния.

    Проверяет подключение к БД, наличие необходимых таблиц, подключение к Redis.
    Результат сохраняется в HealthStateService для мгновенного ответа /health/ready.

    Важно: Эта задача обеспечивает асинхронную архитектуру readiness probe.
    Endpoint /health/ready читает из кеша и отвечает мгновенно, без выполнения
    реальных проверок при каждом запросе.

    Процесс:
    1. Проверка подключения к PostgreSQL
    2. Проверка наличия всех необходимых таблиц
    3. Проверка подключения к Redis
    4. Сохранение результата в HealthStateService
    """
    logger.debug("Readiness health check job started")

    async def _check():
        """
        Внутренняя async функция для проверки состояния.

        ВАЖНО: Использует standalone функции для БД и Redis,
        которые создают собственные подключения для этого event loop.
        Это необходимо, т.к. asyncio.run() создаёт новый event loop,
        и глобальные подключения asyncpg/redis не работают корректно.
        """
        from app.services.health_state_service import (
            health_state_service,
            HealthState,
            DatabaseHealth,
            RedisHealth
        )
        from app.core.database import check_db_connection_standalone, check_db_tables_standalone
        from app.core.redis import check_redis_with_error_standalone
        from datetime import datetime

        # Проверка подключения к БД (standalone версия для background job)
        db_ok = await check_db_connection_standalone()

        # Проверка наличия таблиц (только если подключение успешно)
        if db_ok:
            tables_ok, missing_tables = await check_db_tables_standalone()
        else:
            tables_ok, missing_tables = False, []

        # Проверка подключения к Redis (standalone версия для background job)
        redis_ok, redis_error = await check_redis_with_error_standalone()

        # Формируем состояние БД
        if db_ok and tables_ok:
            db_health = DatabaseHealth(ok=True, error=None, missing_tables=[])
        elif not db_ok:
            db_health = DatabaseHealth(
                ok=False,
                error="Connection failed",
                missing_tables=[]
            )
        else:
            db_health = DatabaseHealth(
                ok=False,
                error=f"Missing tables: {missing_tables}",
                missing_tables=missing_tables
            )

        # Формируем состояние Redis
        redis_health = RedisHealth(ok=redis_ok, error=redis_error)

        # Определяем готовность (только БД критична)
        is_ready = db_health.ok
        reason = None if is_ready else f"Database not ready: {db_health.error}"
        warnings = [f"Redis unavailable: {redis_error}"] if not redis_ok else []

        # Создаем и сохраняем состояние
        state = HealthState(
            database=db_health,
            redis=redis_health,
            last_check=datetime.utcnow(),
            is_ready=is_ready,
            reason=reason,
            warnings=warnings
        )

        health_state_service.update_state(state)

        logger.debug(
            f"Readiness health check completed: is_ready={is_ready}, "
            f"db_ok={db_health.ok}, redis_ok={redis_ok}"
        )

    try:
        asyncio.run(_check())
    except Exception as e:
        logger.error(f"Readiness health check job failed with exception: {e}", exc_info=True)


async def readiness_health_check_async() -> None:
    """
    Асинхронная версия проверки готовности для вызова из async контекста.

    Используется для первичной проверки при startup в lifespan FastAPI,
    где уже есть работающий event loop.

    ВАЖНО: НЕ ИСПОЛЬЗОВАТЬ в APScheduler jobs - там нужен readiness_health_check_job()
    с asyncio.run() для создания отдельного event loop в другом потоке.
    """
    from datetime import datetime
    from app.services.health_state_service import (
        health_state_service, HealthState, DatabaseHealth, RedisHealth
    )
    from app.core.database import check_db_connection, check_db_tables
    from app.core.redis import check_redis_with_error

    try:
        # Проверка подключения к БД
        db_ok = await check_db_connection()

        # Проверка наличия таблиц (только если подключение успешно)
        if db_ok:
            tables_ok, missing_tables = await check_db_tables()
        else:
            tables_ok, missing_tables = False, []

        # Проверка подключения к Redis
        redis_ok, redis_error = await check_redis_with_error()

        # Формируем состояние БД
        if db_ok and tables_ok:
            db_health = DatabaseHealth(ok=True, error=None, missing_tables=[])
        elif not db_ok:
            db_health = DatabaseHealth(
                ok=False,
                error="Connection failed",
                missing_tables=[]
            )
        else:
            db_health = DatabaseHealth(
                ok=False,
                error=f"Missing tables: {missing_tables}",
                missing_tables=missing_tables
            )

        # Формируем состояние Redis
        redis_health = RedisHealth(ok=redis_ok, error=redis_error)

        # Определяем готовность (только БД критична)
        is_ready = db_health.ok
        reason = None if is_ready else f"Database not ready: {db_health.error}"
        warnings = [f"Redis unavailable: {redis_error}"] if not redis_ok else []

        # Создаем и сохраняем состояние
        state = HealthState(
            database=db_health,
            redis=redis_health,
            last_check=datetime.utcnow(),
            is_ready=is_ready,
            reason=reason,
            warnings=warnings
        )

        health_state_service.update_state(state)

        logger.info(
            f"Initial readiness check completed: is_ready={is_ready}, "
            f"db_ok={db_health.ok}, redis_ok={redis_ok}"
        )

    except Exception as e:
        logger.error(f"Initial readiness health check failed: {e}", exc_info=True)


def garbage_collection_job() -> None:
    """
    Background задача для Garbage Collection файлов.

    Выполняется периодически согласно настройкам scheduler.gc_interval_hours.
    Очищает файлы по трём стратегиям:
    1. TTL-based cleanup: удаление temporary файлов с истекшим TTL
    2. Finalized files cleanup: удаление из Edit SE после финализации (+24h safety)
    3. Cleanup queue processing: обработка очереди на удаление

    Note:
        Эта функция запускает async код через asyncio.run(),
        так как APScheduler BackgroundScheduler работает синхронно.
    """
    logger.info("Garbage Collection job started")

    async def _gc():
        """Внутренняя async функция для GC."""
        # Создаем standalone session для нового event loop
        session = await create_standalone_async_session()
        try:
            # Создаем GC service с настройками из config
            gc_service = GarbageCollectorService(
                batch_size=settings.scheduler.gc_batch_size,
                safety_margin_hours=settings.scheduler.gc_safety_margin_hours,
                orphan_grace_days=settings.scheduler.gc_orphan_grace_days,
            )

            # Запускаем GC
            result = await gc_service.run_garbage_collection(session)

            # Логируем результат
            if result.total_failed > 0 or result.errors:
                logger.warning(
                    f"Garbage Collection completed with issues: "
                    f"cleaned={result.total_cleaned}, failed={result.total_failed}, "
                    f"duration={result.duration_seconds:.2f}s, "
                    f"errors={len(result.errors)}"
                )
            else:
                logger.info(
                    f"Garbage Collection completed successfully: "
                    f"cleaned={result.total_cleaned}, duration={result.duration_seconds:.2f}s"
                )

        except Exception as e:
            logger.error(f"Garbage Collection job failed: {e}", exc_info=True)
        finally:
            await session.close()

    try:
        asyncio.run(_gc())
    except Exception as e:
        logger.error(f"Garbage Collection job failed with exception: {e}", exc_info=True)


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

        # Storage Element Publish job для Service Discovery
        if settings.service_discovery.enabled:
            _scheduler.add_job(
                func=storage_element_publish_job,
                trigger=IntervalTrigger(
                    seconds=settings.service_discovery.publish_interval_seconds,
                    timezone=tz
                ),
                id="storage_element_publish",
                name="Storage Element Config Publish",
                replace_existing=True,
                max_instances=1,  # Только одна инстанция job может выполняться одновременно
                coalesce=True,  # Если пропущено несколько запусков, выполнить только один
                misfire_grace_time=60  # 1 минута grace period для missed jobs
            )

            logger.info(
                f"Storage element publish job scheduled: "
                f"interval={settings.service_discovery.publish_interval_seconds}s, "
                f"timezone={settings.scheduler.timezone}"
            )

        # Storage Health Check job - периодическая проверка состояния storage elements
        if settings.scheduler.storage_health_check_enabled:
            _scheduler.add_job(
                func=storage_health_check_job,
                trigger=IntervalTrigger(
                    seconds=settings.scheduler.storage_health_check_interval_seconds,
                    timezone=tz
                ),
                id="storage_health_check",
                name="Storage Element Health Check",
                replace_existing=True,
                max_instances=1,  # Только одна инстанция job может выполняться одновременно
                coalesce=True,  # Если пропущено несколько запусков, выполнить только один
                misfire_grace_time=120  # 2 минуты grace period для missed jobs
            )

            logger.info(
                f"Storage health check job scheduled: "
                f"interval={settings.scheduler.storage_health_check_interval_seconds}s, "
                f"timezone={settings.scheduler.timezone}"
            )

        # Readiness Health Check job - периодическая проверка состояния БД и Redis
        if settings.scheduler.readiness_check_enabled:
            _scheduler.add_job(
                func=readiness_health_check_job,
                trigger=IntervalTrigger(
                    seconds=settings.scheduler.readiness_check_interval_seconds,
                    timezone=tz
                ),
                id="readiness_health_check",
                name="Readiness Health Check",
                replace_existing=True,
                max_instances=1,  # Только одна инстанция job может выполняться одновременно
                coalesce=True,  # Если пропущено несколько запусков, выполнить только один
                misfire_grace_time=30  # 30 секунд grace period для missed jobs
            )

            logger.info(
                f"Readiness health check job scheduled: "
                f"interval={settings.scheduler.readiness_check_interval_seconds}s, "
                f"timezone={settings.scheduler.timezone}"
            )

        # Garbage Collection job - периодическая очистка файлов
        if settings.scheduler.gc_enabled:
            _scheduler.add_job(
                func=garbage_collection_job,
                trigger=IntervalTrigger(
                    hours=settings.scheduler.gc_interval_hours,
                    timezone=tz
                ),
                id="garbage_collection",
                name="Garbage Collection",
                replace_existing=True,
                max_instances=1,  # Только одна инстанция job может выполняться одновременно
                coalesce=True,  # Если пропущено несколько запусков, выполнить только один
                misfire_grace_time=3600  # 1 час grace period для missed jobs
            )

            logger.info(
                f"Garbage Collection job scheduled: "
                f"interval={settings.scheduler.gc_interval_hours}h, "
                f"batch_size={settings.scheduler.gc_batch_size}, "
                f"safety_margin={settings.scheduler.gc_safety_margin_hours}h, "
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
