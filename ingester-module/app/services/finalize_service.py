"""
Ingester Module - Finalize Service.

Sprint 15: Two-Phase Commit сервис для финализации temporary файлов.

Two-Phase Commit Process:
1. COPYING: Начало копирования файла с Edit SE на RW SE
2. COPIED: Файл скопирован на target SE
3. VERIFYING: Проверка checksum source == target
4. COMPLETED: Успешная финализация
5. FAILED: Ошибка на любом этапе
6. ROLLED_BACK: Откат транзакции

Safety Features:
- Checksum verification предотвращает data corruption
- 24-hour safety margin перед cleanup источника
- Transaction log для recovery
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

import httpx

from app.core.config import settings
from app.core.exceptions import (
    StorageElementUnavailableException,
    NoAvailableStorageException
)
from app.core.metrics import (
    record_file_finalization,
    record_finalize_phase,
    update_finalize_in_progress,
    finalize_checksum_mismatch_total,
)
from app.schemas.upload import (
    FinalizeRequest,
    FinalizeResponse,
    FinalizeStatus,
    FinalizeTransactionStatus,
    RetentionPolicy
)
from app.services.auth_service import AuthService

if TYPE_CHECKING:
    from app.services.storage_selector import StorageSelector

logger = logging.getLogger(__name__)

# Константы для Two-Phase Commit
CLEANUP_SAFETY_MARGIN_HOURS = 24  # Время ожидания перед удалением из source SE
MAX_RETRY_ATTEMPTS = 3  # Максимальное количество retry


class FinalizeService:
    """
    Сервис финализации файлов (Two-Phase Commit).

    Sprint 15: Управляет процессом переноса файлов из Edit SE в RW SE.

    Workflow:
    1. Validate: Проверка что файл temporary и существует
    2. Select Target: Выбор RW SE для файла
    3. Copy: Копирование файла на target SE
    4. Verify: Проверка checksum source == target
    5. Update: Обновление metadata (retention_policy → permanent)
    6. Schedule Cleanup: Добавление source в cleanup queue (+24h)

    Usage:
        service = FinalizeService(auth_service)
        await service.initialize(storage_selector)

        response = await service.finalize_file(
            file_id=uuid4(),
            request=FinalizeRequest(),
            user_id="user123"
        )
    """

    def __init__(self, auth_service: AuthService):
        """
        Инициализация FinalizeService.

        Args:
            auth_service: AuthService для аутентификации в SE
        """
        self.auth_service = auth_service
        self._storage_selector: Optional["StorageSelector"] = None
        self._se_clients: dict[str, httpx.AsyncClient] = {}

        # In-memory transaction store (в production - Redis или DB)
        self._transactions: dict[UUID, dict] = {}

    def set_storage_selector(self, storage_selector: "StorageSelector") -> None:
        """
        Установка StorageSelector для выбора target SE.

        Args:
            storage_selector: Инициализированный StorageSelector
        """
        self._storage_selector = storage_selector
        logger.info("StorageSelector injected into FinalizeService")

    async def _get_client_for_endpoint(self, endpoint: str) -> httpx.AsyncClient:
        """
        Получение HTTP клиента для указанного SE endpoint.

        Args:
            endpoint: URL Storage Element

        Returns:
            httpx.AsyncClient: Async HTTP клиент
        """
        if endpoint in self._se_clients:
            return self._se_clients[endpoint]

        client = httpx.AsyncClient(
            base_url=endpoint,
            timeout=settings.storage_element.timeout,
            http2=True
        )
        self._se_clients[endpoint] = client

        logger.debug(f"HTTP client created for SE endpoint", extra={"endpoint": endpoint})
        return client

    async def close(self):
        """Закрытие всех HTTP клиентов."""
        for endpoint, client in self._se_clients.items():
            try:
                await client.aclose()
            except Exception as e:
                logger.warning(f"Error closing SE client", extra={"endpoint": endpoint, "error": str(e)})

        self._se_clients.clear()
        logger.info("FinalizeService clients closed")

    async def finalize_file(
        self,
        file_id: UUID,
        source_se_id: str,
        source_se_endpoint: str,
        file_size: int,
        checksum: str,
        request: FinalizeRequest,
        user_id: str
    ) -> FinalizeResponse:
        """
        Финализация temporary файла (Two-Phase Commit).

        Sprint 15: Основной метод для переноса файла из Edit SE в RW SE.

        Args:
            file_id: UUID файла для финализации
            source_se_id: ID исходного Edit SE
            source_se_endpoint: URL исходного Edit SE
            file_size: Размер файла
            checksum: SHA-256 checksum файла
            request: Параметры финализации
            user_id: ID пользователя

        Returns:
            FinalizeResponse: Результат финализации

        Raises:
            ValueError: Файл не найден или не temporary
            StorageElementUnavailableException: SE недоступен
            NoAvailableStorageException: Нет доступного target SE
        """
        transaction_id = uuid4()
        start_time = time.perf_counter()
        checksum_mismatch = False

        logger.info(
            "Starting file finalization",
            extra={
                "transaction_id": str(transaction_id),
                "file_id": str(file_id),
                "source_se_id": source_se_id,
                "user_id": user_id
            }
        )

        # Увеличиваем счётчик активных транзакций
        update_finalize_in_progress(1)

        # Создаём запись транзакции
        self._transactions[transaction_id] = {
            "transaction_id": transaction_id,
            "file_id": file_id,
            "source_se": source_se_id,
            "target_se": None,
            "status": FinalizeTransactionStatus.COPYING,
            "checksum_source": checksum,
            "checksum_target": None,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None,
            "error_message": None,
            "retry_count": 0,
            "initiated_by": user_id
        }

        try:
            # Phase 1: Выбор target SE
            phase_start = time.perf_counter()
            target_se_endpoint, target_se_id = await self._select_target_se(
                file_size=file_size,
                preferred_se_id=request.target_storage_element_id
            )
            record_finalize_phase("select_target", time.perf_counter() - phase_start)

            self._transactions[transaction_id]["target_se"] = target_se_id

            # Phase 2: Копирование файла
            phase_start = time.perf_counter()
            await self._copy_file(
                transaction_id=transaction_id,
                file_id=file_id,
                source_endpoint=source_se_endpoint,
                target_endpoint=target_se_endpoint
            )
            record_finalize_phase("copy", time.perf_counter() - phase_start)

            self._transactions[transaction_id]["status"] = FinalizeTransactionStatus.COPIED

            # Phase 3: Verification
            self._transactions[transaction_id]["status"] = FinalizeTransactionStatus.VERIFYING

            phase_start = time.perf_counter()
            target_checksum = await self._verify_checksum(
                file_id=file_id,
                target_endpoint=target_se_endpoint
            )
            record_finalize_phase("verify", time.perf_counter() - phase_start)

            self._transactions[transaction_id]["checksum_target"] = target_checksum

            # Проверка checksum
            if checksum != target_checksum:
                checksum_mismatch = True
                raise ValueError(
                    f"Checksum mismatch: source={checksum}, target={target_checksum}"
                )

            # Phase 4: Success
            completed_at = datetime.now(timezone.utc)
            cleanup_scheduled_at = completed_at + timedelta(hours=CLEANUP_SAFETY_MARGIN_HOURS)

            self._transactions[transaction_id]["status"] = FinalizeTransactionStatus.COMPLETED
            self._transactions[transaction_id]["completed_at"] = completed_at

            logger.info(
                "File finalization completed successfully",
                extra={
                    "transaction_id": str(transaction_id),
                    "file_id": str(file_id),
                    "source_se": source_se_id,
                    "target_se": target_se_id,
                    "checksum_verified": True
                }
            )

            # Записываем успешные метрики
            duration = time.perf_counter() - start_time
            record_file_finalization(
                status="success",
                duration_seconds=duration,
                checksum_mismatch=False
            )

            return FinalizeResponse(
                transaction_id=transaction_id,
                file_id=file_id,
                status=FinalizeTransactionStatus.COMPLETED,
                source_storage_element_id=source_se_id,
                target_storage_element_id=target_se_id,
                checksum_verified=True,
                finalized_at=completed_at,
                new_storage_path=f"/files/{file_id}",
                cleanup_scheduled_at=cleanup_scheduled_at
            )

        except Exception as e:
            # Rollback
            error_message = str(e)
            self._transactions[transaction_id]["status"] = FinalizeTransactionStatus.FAILED
            self._transactions[transaction_id]["error_message"] = error_message
            self._transactions[transaction_id]["completed_at"] = datetime.now(timezone.utc)

            logger.error(
                "File finalization failed",
                extra={
                    "transaction_id": str(transaction_id),
                    "file_id": str(file_id),
                    "error": error_message
                }
            )

            # Attempt rollback
            await self._rollback_transaction(transaction_id)

            # Записываем метрики ошибки
            duration = time.perf_counter() - start_time
            record_file_finalization(
                status="failed",
                duration_seconds=duration,
                checksum_mismatch=checksum_mismatch
            )

            return FinalizeResponse(
                transaction_id=transaction_id,
                file_id=file_id,
                status=FinalizeTransactionStatus.FAILED,
                source_storage_element_id=source_se_id,
                target_storage_element_id=self._transactions[transaction_id].get("target_se", ""),
                checksum_verified=False,
                error_message=error_message
            )

        finally:
            # Уменьшаем счётчик активных транзакций
            update_finalize_in_progress(-1)

    async def _select_target_se(
        self,
        file_size: int,
        preferred_se_id: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Выбор target RW SE для финализации.

        Args:
            file_size: Размер файла
            preferred_se_id: Предпочитаемый SE ID (опционально)

        Returns:
            tuple[str, str]: (endpoint, id) выбранного SE

        Raises:
            NoAvailableStorageException: StorageSelector не настроен или нет SE
        """
        # Sprint 16: StorageSelector обязателен, static fallback удалён
        if not self._storage_selector:
            logger.error(
                "StorageSelector not configured - Service Discovery required for finalization",
                extra={"error": "StorageSelector must be set via set_storage_selector()"}
            )
            raise NoAvailableStorageException(
                "StorageSelector not configured. "
                "Service Discovery (Redis or Admin Module) is required for finalization."
            )

        from app.services.storage_selector import RetentionPolicy as SelectorRetentionPolicy

        # Выбираем RW SE для permanent storage
        se_info = await self._storage_selector.select_storage_element(
            file_size=file_size,
            retention_policy=SelectorRetentionPolicy.PERMANENT
        )

        if not se_info:
            raise NoAvailableStorageException(
                f"No available RW Storage Element for file_size={file_size}"
            )

        return se_info.endpoint, se_info.element_id

    async def _copy_file(
        self,
        transaction_id: UUID,
        file_id: UUID,
        source_endpoint: str,
        target_endpoint: str
    ) -> None:
        """
        Копирование файла с source SE на target SE.

        Sprint 15: Phase 1 Two-Phase Commit.

        Args:
            transaction_id: UUID транзакции
            file_id: UUID файла
            source_endpoint: URL source SE
            target_endpoint: URL target SE
        """
        logger.info(
            "Copying file between SEs",
            extra={
                "transaction_id": str(transaction_id),
                "file_id": str(file_id),
                "source": source_endpoint,
                "target": target_endpoint
            }
        )

        # Получаем токен для аутентификации
        access_token = await self.auth_service.get_access_token()

        # Step 1: Download file from source SE
        source_client = await self._get_client_for_endpoint(source_endpoint)

        try:
            download_response = await source_client.get(
                f"/api/v1/files/{file_id}/download",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            download_response.raise_for_status()
            file_content = download_response.content

        except httpx.HTTPStatusError as e:
            raise StorageElementUnavailableException(
                f"Failed to download from source SE: {e.response.status_code}"
            )

        # Step 2: Upload file to target SE
        target_client = await self._get_client_for_endpoint(target_endpoint)

        try:
            upload_response = await target_client.post(
                "/api/v1/files/upload",
                headers={"Authorization": f"Bearer {access_token}"},
                files={"file": (f"{file_id}", file_content, "application/octet-stream")},
                data={
                    "retention_policy": "permanent",
                    "finalize_transaction_id": str(transaction_id)
                }
            )
            upload_response.raise_for_status()

        except httpx.HTTPStatusError as e:
            raise StorageElementUnavailableException(
                f"Failed to upload to target SE: {e.response.status_code}"
            )

        logger.info(
            "File copied successfully",
            extra={
                "transaction_id": str(transaction_id),
                "file_id": str(file_id)
            }
        )

    async def _verify_checksum(
        self,
        file_id: UUID,
        target_endpoint: str
    ) -> str:
        """
        Получение checksum файла с target SE для verification.

        Args:
            file_id: UUID файла
            target_endpoint: URL target SE

        Returns:
            str: SHA-256 checksum файла на target SE
        """
        access_token = await self.auth_service.get_access_token()
        target_client = await self._get_client_for_endpoint(target_endpoint)

        try:
            response = await target_client.get(
                f"/api/v1/files/{file_id}/metadata",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            metadata = response.json()
            return metadata.get("checksum", "")

        except httpx.HTTPStatusError as e:
            raise StorageElementUnavailableException(
                f"Failed to verify checksum: {e.response.status_code}"
            )

    async def _rollback_transaction(self, transaction_id: UUID) -> None:
        """
        Откат транзакции - удаление файла с target SE.

        Args:
            transaction_id: UUID транзакции для отката
        """
        tx = self._transactions.get(transaction_id)
        if not tx or not tx.get("target_se"):
            return

        logger.warning(
            "Rolling back transaction",
            extra={"transaction_id": str(transaction_id)}
        )

        # TODO: Implement actual rollback - delete file from target SE
        # This would require calling DELETE /api/v1/files/{file_id} on target SE

        tx["status"] = FinalizeTransactionStatus.ROLLED_BACK

    async def get_transaction_status(self, transaction_id: UUID) -> Optional[FinalizeStatus]:
        """
        Получение статуса транзакции финализации.

        Args:
            transaction_id: UUID транзакции

        Returns:
            FinalizeStatus или None если не найдена
        """
        tx = self._transactions.get(transaction_id)
        if not tx:
            return None

        # Расчёт progress
        status_progress = {
            FinalizeTransactionStatus.COPYING: 25.0,
            FinalizeTransactionStatus.COPIED: 50.0,
            FinalizeTransactionStatus.VERIFYING: 75.0,
            FinalizeTransactionStatus.COMPLETED: 100.0,
            FinalizeTransactionStatus.FAILED: 0.0,
            FinalizeTransactionStatus.ROLLED_BACK: 0.0
        }

        return FinalizeStatus(
            transaction_id=tx["transaction_id"],
            file_id=tx["file_id"],
            status=tx["status"],
            progress_percent=status_progress.get(tx["status"], 0.0),
            created_at=tx["created_at"],
            completed_at=tx.get("completed_at"),
            error_message=tx.get("error_message")
        )


# Глобальный singleton экземпляр
_finalize_service: Optional[FinalizeService] = None


def get_finalize_service() -> Optional[FinalizeService]:
    """Получение singleton экземпляра FinalizeService."""
    return _finalize_service


def set_finalize_service(service: FinalizeService) -> None:
    """Установка singleton экземпляра FinalizeService."""
    global _finalize_service
    _finalize_service = service
