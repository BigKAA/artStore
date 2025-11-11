"""
Write-Ahead Log Service для обеспечения атомарности операций.

WAL Service обеспечивает:
- Запись намерения перед операцией (начало транзакции)
- Возможность отката при сбое (rollback)
- Аудит всех операций с файлами
- Измерение длительности операций
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import WALException
from app.models.wal import WALTransaction, WALOperationType, WALStatus

logger = logging.getLogger(__name__)


class WALService:
    """
    Сервис управления Write-Ahead Log.

    Координирует транзакции:
    1. Начало: Запись PENDING транзакции в БД
    2. Выполнение: Операция с файлами/данными
    3. Завершение: Коммит (COMMITTED) или откат (ROLLED_BACK)

    Примеры:
        >>> wal = WALService(db_session)
        >>> tx_id = await wal.start_transaction(
        ...     operation_type=WALOperationType.FILE_CREATE,
        ...     file_id=file_uuid,
        ...     operation_data={"path": "/storage/file.pdf"},
        ...     user_id="user123"
        ... )
        >>> try:
        ...     # Выполнение операции
        ...     await wal.commit(tx_id)
        ... except Exception as e:
        ...     await wal.rollback(tx_id, str(e))
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализация WAL Service.

        Args:
            db: Async сессия базы данных
        """
        self.db = db

    async def start_transaction(
        self,
        operation_type: WALOperationType,
        operation_data: Dict[str, Any],
        file_id: Optional[UUID] = None,
        user_id: Optional[str] = None
    ) -> UUID:
        """
        Начать новую транзакцию WAL.

        Создает запись PENDING в БД перед началом операции.
        Это обеспечивает возможность отката при сбое.

        Args:
            operation_type: Тип операции (create, update, delete, etc.)
            operation_data: Данные операции (путь, метаданные, и т.д.)
            file_id: UUID файла (опционально, для файловых операций)
            user_id: User ID инициатора операции (опционально)

        Returns:
            UUID: transaction_id для последующего commit/rollback

        Raises:
            WALException: Если не удалось создать транзакцию

        Примеры:
            >>> tx_id = await wal.start_transaction(
            ...     operation_type=WALOperationType.FILE_CREATE,
            ...     file_id=uuid4(),
            ...     operation_data={
            ...         "storage_path": "2025/01/10/15/",
            ...         "storage_filename": "report.pdf",
            ...         "original_filename": "report.pdf",
            ...         "file_size": 1024000
            ...     },
            ...     user_id="user123"
            ... )
        """
        try:
            # Создание транзакции
            transaction = WALTransaction(
                transaction_id=uuid4(),
                operation_type=operation_type.value,
                status=WALStatus.PENDING.value,
                file_id=file_id,
                operation_data=operation_data,
                user_id=user_id,
                started_at=datetime.utcnow()
            )

            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)

            logger.info(
                "WAL transaction started",
                extra={
                    "transaction_id": str(transaction.transaction_id),
                    "operation_type": operation_type.value,
                    "file_id": str(file_id) if file_id else None,
                    "user_id": user_id
                }
            )

            return transaction.transaction_id

        except Exception as e:
            logger.error(
                f"Failed to start WAL transaction: {e}",
                extra={
                    "operation_type": operation_type.value,
                    "error": str(e)
                }
            )
            raise WALException(
                message="Failed to start transaction",
                error_code="WAL_START_FAILED",
                details={"operation_type": operation_type.value, "error": str(e)}
            )

    async def commit(
        self,
        transaction_id: UUID,
        result_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Завершить транзакцию успешно (COMMITTED).

        Обновляет статус транзакции на COMMITTED и вычисляет длительность.
        Дополнительно может сохранить результаты операции.

        Args:
            transaction_id: UUID транзакции из start_transaction()
            result_data: Дополнительные данные результата (опционально)

        Raises:
            WALException: Если транзакция не найдена или уже завершена

        Примеры:
            >>> await wal.commit(
            ...     tx_id,
            ...     result_data={"checksum": "sha256_hash"}
            ... )
        """
        try:
            # Получение транзакции
            result = await self.db.execute(
                select(WALTransaction).where(
                    WALTransaction.transaction_id == transaction_id
                )
            )
            transaction = result.scalar_one_or_none()

            if not transaction:
                raise WALException(
                    message=f"Transaction {transaction_id} not found",
                    error_code="WAL_TX_NOT_FOUND",
                    details={"transaction_id": str(transaction_id)}
                )

            if transaction.status != WALStatus.PENDING.value:
                raise WALException(
                    message=f"Transaction {transaction_id} already completed with status {transaction.status}",
                    error_code="WAL_TX_ALREADY_COMPLETED",
                    details={
                        "transaction_id": str(transaction_id),
                        "current_status": transaction.status
                    }
                )

            # Обновление статуса
            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - transaction.started_at).total_seconds() * 1000)

            transaction.status = WALStatus.COMMITTED.value
            transaction.completed_at = completed_at
            transaction.duration_ms = duration_ms

            # Добавление результатов операции если переданы
            if result_data:
                transaction.operation_data = {
                    **transaction.operation_data,
                    "result": result_data
                }

            await self.db.commit()

            logger.info(
                "WAL transaction committed",
                extra={
                    "transaction_id": str(transaction_id),
                    "operation_type": transaction.operation_type,
                    "duration_ms": duration_ms,
                    "file_id": str(transaction.file_id) if transaction.file_id else None
                }
            )

        except WALException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to commit WAL transaction: {e}",
                extra={
                    "transaction_id": str(transaction_id),
                    "error": str(e)
                }
            )
            raise WALException(
                message="Failed to commit transaction",
                error_code="WAL_COMMIT_FAILED",
                details={"transaction_id": str(transaction_id), "error": str(e)}
            )

    async def rollback(
        self,
        transaction_id: UUID,
        error_message: str
    ) -> None:
        """
        Откатить транзакцию при ошибке (ROLLED_BACK).

        Обновляет статус транзакции на ROLLED_BACK и сохраняет
        информацию об ошибке для анализа.

        Args:
            transaction_id: UUID транзакции из start_transaction()
            error_message: Описание ошибки, вызвавшей откат

        Raises:
            WALException: Если транзакция не найдена или уже завершена

        Примеры:
            >>> try:
            ...     # Выполнение операции
            ...     pass
            ... except Exception as e:
            ...     await wal.rollback(tx_id, str(e))
        """
        try:
            # Получение транзакции
            result = await self.db.execute(
                select(WALTransaction).where(
                    WALTransaction.transaction_id == transaction_id
                )
            )
            transaction = result.scalar_one_or_none()

            if not transaction:
                raise WALException(
                    message=f"Transaction {transaction_id} not found",
                    error_code="WAL_TX_NOT_FOUND",
                    details={"transaction_id": str(transaction_id)}
                )

            if transaction.status != WALStatus.PENDING.value:
                raise WALException(
                    message=f"Transaction {transaction_id} already completed with status {transaction.status}",
                    error_code="WAL_TX_ALREADY_COMPLETED",
                    details={
                        "transaction_id": str(transaction_id),
                        "current_status": transaction.status
                    }
                )

            # Обновление статуса
            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - transaction.started_at).total_seconds() * 1000)

            transaction.status = WALStatus.ROLLED_BACK.value
            transaction.completed_at = completed_at
            transaction.duration_ms = duration_ms
            transaction.error_message = error_message

            await self.db.commit()

            logger.warning(
                "WAL transaction rolled back",
                extra={
                    "transaction_id": str(transaction_id),
                    "operation_type": transaction.operation_type,
                    "duration_ms": duration_ms,
                    "error": error_message,
                    "file_id": str(transaction.file_id) if transaction.file_id else None
                }
            )

        except WALException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to rollback WAL transaction: {e}",
                extra={
                    "transaction_id": str(transaction_id),
                    "error": str(e)
                }
            )
            raise WALException(
                message="Failed to rollback transaction",
                error_code="WAL_ROLLBACK_FAILED",
                details={"transaction_id": str(transaction_id), "error": str(e)}
            )

    async def mark_failed(
        self,
        transaction_id: UUID,
        error_message: str
    ) -> None:
        """
        Пометить транзакцию как FAILED (ошибка без отката).

        Используется когда операция не может быть откачена
        или откат невозможен по техническим причинам.

        Args:
            transaction_id: UUID транзакции из start_transaction()
            error_message: Описание ошибки

        Raises:
            WALException: Если транзакция не найдена или уже завершена
        """
        try:
            # Получение транзакции
            result = await self.db.execute(
                select(WALTransaction).where(
                    WALTransaction.transaction_id == transaction_id
                )
            )
            transaction = result.scalar_one_or_none()

            if not transaction:
                raise WALException(
                    message=f"Transaction {transaction_id} not found",
                    error_code="WAL_TX_NOT_FOUND",
                    details={"transaction_id": str(transaction_id)}
                )

            # Обновление статуса
            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - transaction.started_at).total_seconds() * 1000)

            transaction.status = WALStatus.FAILED.value
            transaction.completed_at = completed_at
            transaction.duration_ms = duration_ms
            transaction.error_message = error_message

            await self.db.commit()

            logger.error(
                "WAL transaction failed",
                extra={
                    "transaction_id": str(transaction_id),
                    "operation_type": transaction.operation_type,
                    "duration_ms": duration_ms,
                    "error": error_message,
                    "file_id": str(transaction.file_id) if transaction.file_id else None
                }
            )

        except WALException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to mark WAL transaction as failed: {e}",
                extra={
                    "transaction_id": str(transaction_id),
                    "error": str(e)
                }
            )
            raise WALException(
                message="Failed to mark transaction as failed",
                error_code="WAL_MARK_FAILED_ERROR",
                details={"transaction_id": str(transaction_id), "error": str(e)}
            )

    async def get_transaction(
        self,
        transaction_id: UUID
    ) -> Optional[WALTransaction]:
        """
        Получить транзакцию по ID.

        Args:
            transaction_id: UUID транзакции

        Returns:
            WALTransaction или None если не найдена
        """
        try:
            result = await self.db.execute(
                select(WALTransaction).where(
                    WALTransaction.transaction_id == transaction_id
                )
            )
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(
                f"Failed to get WAL transaction: {e}",
                extra={
                    "transaction_id": str(transaction_id),
                    "error": str(e)
                }
            )
            return None

    async def get_pending_transactions(
        self,
        limit: int = 100
    ) -> list[WALTransaction]:
        """
        Получить все незавершенные транзакции (PENDING).

        Используется для recovery после сбоев.

        Args:
            limit: Максимальное количество транзакций

        Returns:
            Список PENDING транзакций
        """
        try:
            result = await self.db.execute(
                select(WALTransaction)
                .where(WALTransaction.status == WALStatus.PENDING.value)
                .order_by(WALTransaction.started_at)
                .limit(limit)
            )
            return list(result.scalars().all())

        except Exception as e:
            logger.error(
                f"Failed to get pending WAL transactions: {e}",
                extra={"error": str(e)}
            )
            return []
