"""
Atomic file writing utilities с Write-Ahead Logging (WAL) для Storage Element.

Обеспечивает атомарность операций записи файлов атрибутов через:
- Write-Ahead Log (WAL) для транзакционности
- Временные файлы с fsync для гарантии записи на диск
- Атомарное переименование (POSIX rename() guarantee)
"""

import os
import json
from uuid import uuid4, UUID
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum


class OperationType(str, Enum):
    """Типы операций в WAL."""
    UPLOAD = "upload"
    DELETE = "delete"
    UPDATE_METADATA = "update_metadata"
    MODE_CHANGE = "mode_change"


class OperationStatus(str, Enum):
    """Статусы операций в WAL."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class WALEntry:
    """
    Запись в Write-Ahead Log для транзакционности операций.

    WAL обеспечивает возможность восстановления после сбоев и отката операций.
    """

    def __init__(
        self,
        transaction_id: UUID,
        operation_type: OperationType,
        payload: Dict[str, Any],
        saga_id: Optional[str] = None,
        file_id: Optional[UUID] = None,
        compensation_data: Optional[Dict[str, Any]] = None
    ):
        """
        Инициализация WAL entry.

        Args:
            transaction_id: Уникальный ID транзакции
            operation_type: Тип операции (upload, delete, update_metadata, mode_change)
            payload: Данные операции (сериализуемые в JSON)
            saga_id: ID Saga для распределенных транзакций
            file_id: ID файла (если применимо)
            compensation_data: Данные для компенсирующей операции при rollback
        """
        self.transaction_id = transaction_id
        self.operation_type = operation_type
        self.operation_status = OperationStatus.PENDING
        self.payload = payload
        self.saga_id = saga_id
        self.file_id = file_id
        self.compensation_data = compensation_data
        self.created_at = datetime.now(timezone.utc)
        self.committed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация WAL entry в словарь для JSON."""
        return {
            "transaction_id": str(self.transaction_id),
            "operation_type": self.operation_type.value,
            "operation_status": self.operation_status.value,
            "payload": self.payload,
            "saga_id": self.saga_id,
            "file_id": str(self.file_id) if self.file_id else None,
            "compensation_data": self.compensation_data,
            "created_at": self.created_at.isoformat(),
            "committed_at": self.committed_at.isoformat() if self.committed_at else None
        }

    def mark_in_progress(self) -> None:
        """Помечает операцию как выполняющуюся."""
        self.operation_status = OperationStatus.IN_PROGRESS

    def mark_committed(self) -> None:
        """Помечает операцию как успешно завершенную."""
        self.operation_status = OperationStatus.COMMITTED
        self.committed_at = datetime.now(timezone.utc)

    def mark_failed(self) -> None:
        """Помечает операцию как неудачную."""
        self.operation_status = OperationStatus.FAILED

    def mark_rolled_back(self) -> None:
        """Помечает операцию как откаченную."""
        self.operation_status = OperationStatus.ROLLED_BACK


class WALManager:
    """
    Менеджер Write-Ahead Log для транзакционных операций.

    В production версии WAL хранится в PostgreSQL таблице `storage_elem_01_wal`.
    Для standalone режима и тестирования WAL записывается в файл.
    """

    def __init__(self, wal_dir: Optional[Path] = None):
        """
        Инициализация WAL Manager.

        Args:
            wal_dir: Директория для хранения WAL файлов (для standalone режима)
                     Если None, используется in-memory хранилище для тестов
        """
        self.wal_dir = wal_dir
        self.in_memory_wal: Dict[UUID, WALEntry] = {}

        if wal_dir:
            wal_dir.mkdir(parents=True, exist_ok=True)

    def write_wal_entry(self, entry: WALEntry) -> None:
        """
        Записывает WAL entry в хранилище.

        Args:
            entry: WAL запись для сохранения

        Raises:
            OSError: Если запись WAL не удалась
        """
        if self.wal_dir:
            # Standalone режим - запись в файл
            wal_file = self.wal_dir / f"wal_{entry.transaction_id}.json"
            wal_data = json.dumps(entry.to_dict(), indent=2, ensure_ascii=False)

            # Атомарная запись WAL entry
            temp_file = self.wal_dir / f"wal_{entry.transaction_id}.tmp"

            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(wal_data)
                    f.flush()
                    os.fsync(f.fileno())

                os.rename(temp_file, wal_file)
            except Exception as e:
                if temp_file.exists():
                    temp_file.unlink()
                raise OSError(f"Failed to write WAL entry: {e}") from e
        else:
            # In-memory для тестов
            self.in_memory_wal[entry.transaction_id] = entry

    def update_wal_status(
        self,
        transaction_id: UUID,
        status: OperationStatus
    ) -> None:
        """
        Обновляет статус WAL entry.

        Args:
            transaction_id: ID транзакции
            status: Новый статус операции

        Raises:
            KeyError: Если транзакция не найдена
        """
        if self.wal_dir:
            wal_file = self.wal_dir / f"wal_{transaction_id}.json"
            if not wal_file.exists():
                raise KeyError(f"WAL entry not found: {transaction_id}")

            with open(wal_file, 'r', encoding='utf-8') as f:
                wal_data = json.load(f)

            wal_data["operation_status"] = status.value
            if status == OperationStatus.COMMITTED:
                wal_data["committed_at"] = datetime.now(timezone.utc).isoformat()

            # Атомарная перезапись
            temp_file = self.wal_dir / f"wal_{transaction_id}.tmp"
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(wal_data, indent=2, ensure_ascii=False))
                    f.flush()
                    os.fsync(f.fileno())

                os.rename(temp_file, wal_file)
            except Exception as e:
                if temp_file.exists():
                    temp_file.unlink()
                raise OSError(f"Failed to update WAL status: {e}") from e
        else:
            # In-memory обновление
            if transaction_id not in self.in_memory_wal:
                raise KeyError(f"WAL entry not found: {transaction_id}")

            entry = self.in_memory_wal[transaction_id]
            if status == OperationStatus.COMMITTED:
                entry.mark_committed()
            elif status == OperationStatus.FAILED:
                entry.mark_failed()
            elif status == OperationStatus.ROLLED_BACK:
                entry.mark_rolled_back()
            elif status == OperationStatus.IN_PROGRESS:
                entry.mark_in_progress()

    def get_wal_entry(self, transaction_id: UUID) -> Optional[WALEntry]:
        """
        Получает WAL entry по transaction_id.

        Args:
            transaction_id: ID транзакции

        Returns:
            WALEntry или None если не найдена
        """
        if self.wal_dir:
            wal_file = self.wal_dir / f"wal_{transaction_id}.json"
            if not wal_file.exists():
                return None

            with open(wal_file, 'r', encoding='utf-8') as f:
                wal_data = json.load(f)

            # Десериализация (упрощенная версия для standalone режима)
            entry = WALEntry(
                transaction_id=UUID(wal_data["transaction_id"]),
                operation_type=OperationType(wal_data["operation_type"]),
                payload=wal_data["payload"],
                saga_id=wal_data.get("saga_id"),
                file_id=UUID(wal_data["file_id"]) if wal_data.get("file_id") else None,
                compensation_data=wal_data.get("compensation_data")
            )
            entry.operation_status = OperationStatus(wal_data["operation_status"])
            return entry
        else:
            return self.in_memory_wal.get(transaction_id)


def write_attr_file_atomic(
    target_path: str | Path,
    attributes: Dict[str, Any],
    max_size_bytes: int = 4096,
    wal_manager: Optional[WALManager] = None,
    transaction_id: Optional[UUID] = None
) -> UUID:
    """
    Атомарная запись файла атрибутов через WAL pattern.

    Протокол: WAL → Temp file → fsync → Atomic rename → WAL commit

    Args:
        target_path: Путь к целевому attr.json файлу
        attributes: Словарь атрибутов для записи
        max_size_bytes: Максимальный размер (default: 4KB для атомарности filesystem)
        wal_manager: WAL менеджер для транзакционности (опционально)
        transaction_id: ID транзакции (генерируется автоматически если не указан)

    Returns:
        UUID: ID транзакции

    Raises:
        ValueError: Если размер атрибутов превышает max_size_bytes
        OSError: Если операция записи не удалась

    Examples:
        >>> attrs = {
        ...     "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        ...     "original_filename": "report.pdf",
        ...     "file_size": 1048576,
        ...     "sha256": "e3b0c44..."
        ... }
        >>> tx_id = write_attr_file_atomic("/data/2025/11/08/10/file.attr.json", attrs)

        >>> # С WAL для восстановления после сбоев
        >>> wal_mgr = WALManager(Path("/data/wal"))
        >>> tx_id = write_attr_file_atomic(
        ...     "/data/file.attr.json",
        ...     attrs,
        ...     wal_manager=wal_mgr
        ... )
    """
    target_path = Path(target_path)

    # Генерация transaction_id если не указан
    if transaction_id is None:
        transaction_id = uuid4()

    # Валидация размера (критично для атомарности на filesystem уровне)
    attrs_json = json.dumps(attributes, indent=2, ensure_ascii=False)
    attrs_bytes = attrs_json.encode('utf-8')

    if len(attrs_bytes) > max_size_bytes:
        raise ValueError(
            f"Attributes size {len(attrs_bytes)} bytes exceeds "
            f"maximum {max_size_bytes} bytes. "
            f"Атомарность гарантируется только для файлов <= 4KB."
        )

    # 1. Запись в WAL (если WAL manager предоставлен)
    if wal_manager:
        wal_entry = WALEntry(
            transaction_id=transaction_id,
            operation_type=OperationType.UPDATE_METADATA,
            payload={
                "target_path": str(target_path),
                "attributes": attributes,
                "size_bytes": len(attrs_bytes)
            },
            compensation_data={
                "action": "delete_attr_file",
                "path": str(target_path)
            }
        )
        wal_manager.write_wal_entry(wal_entry)
        wal_manager.update_wal_status(transaction_id, OperationStatus.IN_PROGRESS)

    # Создание директории если не существует
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Создание временного файла с уникальным именем
    temp_file = target_path.parent / f"{target_path.stem}.{uuid4().hex[:8]}.tmp"

    try:
        # 3. Запись в временный файл с fsync (принудительная запись на диск)
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(attrs_json)
            f.flush()
            # fsync гарантирует что данные записаны на физический носитель
            os.fsync(f.fileno())

        # 4. Атомарное переименование (POSIX rename() гарантия)
        # На POSIX системах rename() атомарна если src и dst на одной filesystem
        os.rename(temp_file, target_path)

        # 5. Commit WAL entry
        if wal_manager:
            wal_manager.update_wal_status(transaction_id, OperationStatus.COMMITTED)

        return transaction_id

    except Exception as e:
        # Rollback: очистка временного файла при ошибке
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass  # Best effort cleanup

        # Пометка WAL как failed
        if wal_manager:
            try:
                wal_manager.update_wal_status(transaction_id, OperationStatus.FAILED)
            except Exception:
                pass  # Best effort WAL update

        raise OSError(f"Failed to write attr.json atomically: {e}") from e


def read_attr_file(attr_path: str | Path) -> Dict[str, Any]:
    """
    Читает файл атрибутов.

    Args:
        attr_path: Путь к attr.json файлу

    Returns:
        Dict: Атрибуты файла

    Raises:
        FileNotFoundError: Если файл не существует
        json.JSONDecodeError: Если JSON невалиден

    Examples:
        >>> attrs = read_attr_file("/data/2025/11/08/10/file.attr.json")
        >>> print(attrs["original_filename"])
        'report.pdf'
    """
    attr_path = Path(attr_path)

    if not attr_path.exists():
        raise FileNotFoundError(f"Attr file not found: {attr_path}")

    with open(attr_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def delete_attr_file_atomic(
    attr_path: str | Path,
    wal_manager: Optional[WALManager] = None,
    transaction_id: Optional[UUID] = None
) -> UUID:
    """
    Атомарное удаление файла атрибутов через WAL.

    Args:
        attr_path: Путь к attr.json файлу
        wal_manager: WAL менеджер для транзакционности
        transaction_id: ID транзакции

    Returns:
        UUID: ID транзакции

    Raises:
        FileNotFoundError: Если файл не существует
        OSError: Если удаление не удалось
    """
    attr_path = Path(attr_path)

    if transaction_id is None:
        transaction_id = uuid4()

    if not attr_path.exists():
        raise FileNotFoundError(f"Attr file not found: {attr_path}")

    # Сохранение backup для возможности восстановления
    backup_data = None
    if wal_manager:
        try:
            backup_data = read_attr_file(attr_path)
        except Exception:
            backup_data = None

        wal_entry = WALEntry(
            transaction_id=transaction_id,
            operation_type=OperationType.DELETE,
            payload={"attr_path": str(attr_path)},
            compensation_data={
                "action": "restore_attr_file",
                "path": str(attr_path),
                "content": backup_data
            }
        )
        wal_manager.write_wal_entry(wal_entry)
        wal_manager.update_wal_status(transaction_id, OperationStatus.IN_PROGRESS)

    try:
        # Атомарное удаление
        attr_path.unlink()

        # Commit WAL
        if wal_manager:
            wal_manager.update_wal_status(transaction_id, OperationStatus.COMMITTED)

        return transaction_id

    except Exception as e:
        if wal_manager:
            wal_manager.update_wal_status(transaction_id, OperationStatus.FAILED)
        raise OSError(f"Failed to delete attr file: {e}") from e
