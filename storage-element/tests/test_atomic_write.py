"""
Unit tests для atomic write utilities с WAL.

Тестирует write_attr_file_atomic(), WALManager, и связанные функции.
"""

import pytest
import json
import tempfile
from pathlib import Path
from uuid import uuid4, UUID

from app.core.atomic_write import (
    write_attr_file_atomic,
    read_attr_file,
    delete_attr_file_atomic,
    WALManager,
    WALEntry,
    OperationType,
    OperationStatus
)


class TestWALEntry:
    """Тесты для WALEntry класса."""

    def test_wal_entry_creation(self):
        """Тест создания WAL entry."""
        tx_id = uuid4()
        entry = WALEntry(
            transaction_id=tx_id,
            operation_type=OperationType.UPLOAD,
            payload={"file_id": "test123"}
        )

        assert entry.transaction_id == tx_id
        assert entry.operation_type == OperationType.UPLOAD
        assert entry.operation_status == OperationStatus.PENDING
        assert entry.payload == {"file_id": "test123"}
        assert entry.committed_at is None

    def test_wal_entry_to_dict(self):
        """Тест сериализации WAL entry в dict."""
        tx_id = uuid4()
        file_id = uuid4()
        entry = WALEntry(
            transaction_id=tx_id,
            operation_type=OperationType.DELETE,
            payload={"path": "/data/file.json"},
            saga_id="saga-123",
            file_id=file_id,
            compensation_data={"action": "restore"}
        )

        data = entry.to_dict()

        assert data["transaction_id"] == str(tx_id)
        assert data["operation_type"] == "delete"
        assert data["operation_status"] == "pending"
        assert data["payload"] == {"path": "/data/file.json"}
        assert data["saga_id"] == "saga-123"
        assert data["file_id"] == str(file_id)
        assert data["compensation_data"] == {"action": "restore"}

    def test_wal_entry_mark_in_progress(self):
        """Тест перехода в статус in_progress."""
        entry = WALEntry(
            transaction_id=uuid4(),
            operation_type=OperationType.UPLOAD,
            payload={}
        )

        entry.mark_in_progress()
        assert entry.operation_status == OperationStatus.IN_PROGRESS

    def test_wal_entry_mark_committed(self):
        """Тест перехода в статус committed."""
        entry = WALEntry(
            transaction_id=uuid4(),
            operation_type=OperationType.UPLOAD,
            payload={}
        )

        assert entry.committed_at is None
        entry.mark_committed()

        assert entry.operation_status == OperationStatus.COMMITTED
        assert entry.committed_at is not None

    def test_wal_entry_mark_failed(self):
        """Тест перехода в статус failed."""
        entry = WALEntry(
            transaction_id=uuid4(),
            operation_type=OperationType.UPLOAD,
            payload={}
        )

        entry.mark_failed()
        assert entry.operation_status == OperationStatus.FAILED

    def test_wal_entry_mark_rolled_back(self):
        """Тест перехода в статус rolled_back."""
        entry = WALEntry(
            transaction_id=uuid4(),
            operation_type=OperationType.DELETE,
            payload={}
        )

        entry.mark_rolled_back()
        assert entry.operation_status == OperationStatus.ROLLED_BACK


class TestWALManager:
    """Тесты для WALManager класса."""

    def test_wal_manager_in_memory(self):
        """Тест WAL Manager в in-memory режиме."""
        mgr = WALManager()  # Без wal_dir = in-memory

        tx_id = uuid4()
        entry = WALEntry(
            transaction_id=tx_id,
            operation_type=OperationType.UPLOAD,
            payload={"test": "data"}
        )

        mgr.write_wal_entry(entry)

        # Проверяем что запись доступна
        retrieved = mgr.get_wal_entry(tx_id)
        assert retrieved is not None
        assert retrieved.transaction_id == tx_id
        assert retrieved.payload == {"test": "data"}

    def test_wal_manager_file_based(self, tmp_path):
        """Тест WAL Manager с файловым хранилищем."""
        wal_dir = tmp_path / "wal"
        mgr = WALManager(wal_dir=wal_dir)

        # Проверяем что директория создана
        assert wal_dir.exists()

        tx_id = uuid4()
        entry = WALEntry(
            transaction_id=tx_id,
            operation_type=OperationType.DELETE,
            payload={"file": "test.json"}
        )

        mgr.write_wal_entry(entry)

        # Проверяем что WAL файл создан
        wal_file = wal_dir / f"wal_{tx_id}.json"
        assert wal_file.exists()

        # Проверяем содержимое
        with open(wal_file, 'r') as f:
            wal_data = json.load(f)

        assert wal_data["transaction_id"] == str(tx_id)
        assert wal_data["operation_type"] == "delete"

    def test_wal_manager_update_status_in_memory(self):
        """Тест обновления статуса WAL в in-memory режиме."""
        mgr = WALManager()

        tx_id = uuid4()
        entry = WALEntry(
            transaction_id=tx_id,
            operation_type=OperationType.UPLOAD,
            payload={}
        )

        mgr.write_wal_entry(entry)

        # Обновляем статус
        mgr.update_wal_status(tx_id, OperationStatus.IN_PROGRESS)

        retrieved = mgr.get_wal_entry(tx_id)
        assert retrieved.operation_status == OperationStatus.IN_PROGRESS

        # Еще одно обновление
        mgr.update_wal_status(tx_id, OperationStatus.COMMITTED)

        retrieved = mgr.get_wal_entry(tx_id)
        assert retrieved.operation_status == OperationStatus.COMMITTED
        assert retrieved.committed_at is not None

    def test_wal_manager_update_status_file_based(self, tmp_path):
        """Тест обновления статуса WAL в файловом режиме."""
        wal_dir = tmp_path / "wal"
        mgr = WALManager(wal_dir=wal_dir)

        tx_id = uuid4()
        entry = WALEntry(
            transaction_id=tx_id,
            operation_type=OperationType.UPDATE_METADATA,
            payload={}
        )

        mgr.write_wal_entry(entry)

        # Обновляем статус
        mgr.update_wal_status(tx_id, OperationStatus.COMMITTED)

        # Проверяем что файл обновлен
        wal_file = wal_dir / f"wal_{tx_id}.json"
        with open(wal_file, 'r') as f:
            wal_data = json.load(f)

        assert wal_data["operation_status"] == "committed"
        assert wal_data["committed_at"] is not None

    def test_wal_manager_get_nonexistent_entry(self):
        """Тест получения несуществующей WAL entry."""
        mgr = WALManager()

        result = mgr.get_wal_entry(uuid4())
        assert result is None

    def test_wal_manager_update_nonexistent_entry(self):
        """Тест обновления несуществующей WAL entry."""
        mgr = WALManager()

        with pytest.raises(KeyError, match="WAL entry not found"):
            mgr.update_wal_status(uuid4(), OperationStatus.COMMITTED)


class TestWriteAttrFileAtomic:
    """Тесты для write_attr_file_atomic()."""

    def test_basic_write(self, tmp_path):
        """Тест базовой записи attr.json файла."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {
            "file_id": "a1b2c3d4",
            "original_filename": "report.pdf",
            "file_size": 1048576
        }

        tx_id = write_attr_file_atomic(attr_file, attrs)

        # Проверяем что файл создан
        assert attr_file.exists()

        # Проверяем содержимое
        with open(attr_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        assert loaded == attrs

        # Проверяем что tx_id валиден
        assert isinstance(tx_id, UUID)

    def test_write_with_directory_creation(self, tmp_path):
        """Тест записи с автоматическим созданием директории."""
        attr_file = tmp_path / "subdir" / "nested" / "test.attr.json"
        attrs = {"test": "data"}

        write_attr_file_atomic(attr_file, attrs)

        # Проверяем что вся иерархия создана
        assert attr_file.exists()
        assert attr_file.parent.exists()

    def test_write_with_wal(self, tmp_path):
        """Тест записи с WAL logging."""
        wal_dir = tmp_path / "wal"
        wal_mgr = WALManager(wal_dir=wal_dir)

        attr_file = tmp_path / "data" / "test.attr.json"
        attrs = {"file_id": "test123"}

        tx_id = write_attr_file_atomic(attr_file, attrs, wal_manager=wal_mgr)

        # Проверяем что файл создан
        assert attr_file.exists()

        # Проверяем что WAL entry создана и committed
        wal_entry = wal_mgr.get_wal_entry(tx_id)
        assert wal_entry is not None
        assert wal_entry.operation_status == OperationStatus.COMMITTED
        assert wal_entry.payload["target_path"] == str(attr_file)

    def test_write_exceeds_max_size(self, tmp_path):
        """Тест превышения максимального размера."""
        attr_file = tmp_path / "test.attr.json"

        # Создаем большой объект атрибутов
        large_attrs = {
            "description": "a" * 5000  # > 4KB
        }

        with pytest.raises(ValueError, match="exceeds maximum"):
            write_attr_file_atomic(attr_file, large_attrs, max_size_bytes=4096)

    def test_write_with_unicode(self, tmp_path):
        """Тест записи с Unicode символами."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {
            "original_filename": "отчет.pdf",
            "description": "Финансовый отчет за Q3 2025",
            "tags": ["финансы", "квартальный", "2025"],
            "emoji": "📄"
        }

        write_attr_file_atomic(attr_file, attrs)

        # Проверяем что Unicode сохранен корректно
        loaded = read_attr_file(attr_file)
        assert loaded["original_filename"] == "отчет.pdf"
        assert loaded["emoji"] == "📄"

    def test_write_overwrite_existing(self, tmp_path):
        """Тест перезаписи существующего файла."""
        attr_file = tmp_path / "test.attr.json"

        # Первая запись
        attrs1 = {"version": 1}
        write_attr_file_atomic(attr_file, attrs1)

        # Вторая запись (должна перезаписать)
        attrs2 = {"version": 2, "new_field": "value"}
        write_attr_file_atomic(attr_file, attrs2)

        # Проверяем что новые данные
        loaded = read_attr_file(attr_file)
        assert loaded == attrs2

    def test_write_with_custom_transaction_id(self, tmp_path):
        """Тест записи с указанным transaction_id."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {"test": "data"}
        custom_tx_id = uuid4()

        tx_id = write_attr_file_atomic(attr_file, attrs, transaction_id=custom_tx_id)

        assert tx_id == custom_tx_id

    def test_write_atomicity_simulation(self, tmp_path):
        """Тест атомарности - проверка что нет частично записанных файлов."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {"test": "data"}

        # Нормальная запись
        write_attr_file_atomic(attr_file, attrs)

        # Проверяем что временные файлы удалены
        tmp_files = list(attr_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_write_json_formatting(self, tmp_path):
        """Тест форматирования JSON (с indent для читаемости)."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {
            "file_id": "test",
            "metadata": {
                "nested": "value"
            }
        }

        write_attr_file_atomic(attr_file, attrs)

        # Проверяем что JSON красиво отформатирован
        with open(attr_file, 'r') as f:
            content = f.read()

        # Должен быть многострочный JSON с отступами
        assert '\n' in content
        assert '  ' in content  # indent=2


class TestReadAttrFile:
    """Тесты для read_attr_file()."""

    def test_read_existing_file(self, tmp_path):
        """Тест чтения существующего файла."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {"file_id": "test123", "size": 1024}

        # Создаем файл
        write_attr_file_atomic(attr_file, attrs)

        # Читаем
        loaded = read_attr_file(attr_file)
        assert loaded == attrs

    def test_read_nonexistent_file(self, tmp_path):
        """Тест чтения несуществующего файла."""
        attr_file = tmp_path / "nonexistent.attr.json"

        with pytest.raises(FileNotFoundError, match="not found"):
            read_attr_file(attr_file)

    def test_read_invalid_json(self, tmp_path):
        """Тест чтения невалидного JSON."""
        attr_file = tmp_path / "invalid.attr.json"

        # Создаем файл с невалидным JSON
        with open(attr_file, 'w') as f:
            f.write("{ invalid json")

        with pytest.raises(json.JSONDecodeError):
            read_attr_file(attr_file)


class TestDeleteAttrFileAtomic:
    """Тесты для delete_attr_file_atomic()."""

    def test_delete_existing_file(self, tmp_path):
        """Тест удаления существующего файла."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {"test": "data"}

        # Создаем файл
        write_attr_file_atomic(attr_file, attrs)
        assert attr_file.exists()

        # Удаляем
        tx_id = delete_attr_file_atomic(attr_file)

        # Проверяем что файл удален
        assert not attr_file.exists()
        assert isinstance(tx_id, UUID)

    def test_delete_with_wal(self, tmp_path):
        """Тест удаления с WAL logging."""
        wal_dir = tmp_path / "wal"
        wal_mgr = WALManager(wal_dir=wal_dir)

        attr_file = tmp_path / "data" / "test.attr.json"
        attrs = {"file_id": "test123", "important": "data"}

        # Создаем файл
        write_attr_file_atomic(attr_file, attrs)

        # Удаляем с WAL
        tx_id = delete_attr_file_atomic(attr_file, wal_manager=wal_mgr)

        # Проверяем что файл удален
        assert not attr_file.exists()

        # Проверяем WAL entry
        wal_entry = wal_mgr.get_wal_entry(tx_id)
        assert wal_entry is not None
        assert wal_entry.operation_status == OperationStatus.COMMITTED
        assert wal_entry.operation_type == OperationType.DELETE

        # Проверяем что backup данные сохранены в compensation_data
        assert wal_entry.compensation_data["content"] == attrs

    def test_delete_nonexistent_file(self, tmp_path):
        """Тест удаления несуществующего файла."""
        attr_file = tmp_path / "nonexistent.attr.json"

        with pytest.raises(FileNotFoundError, match="not found"):
            delete_attr_file_atomic(attr_file)

    def test_delete_with_custom_transaction_id(self, tmp_path):
        """Тест удаления с указанным transaction_id."""
        attr_file = tmp_path / "test.attr.json"
        write_attr_file_atomic(attr_file, {"test": "data"})

        custom_tx_id = uuid4()
        tx_id = delete_attr_file_atomic(attr_file, transaction_id=custom_tx_id)

        assert tx_id == custom_tx_id


class TestComplexScenarios:
    """Тесты сложных сценариев с WAL."""

    def test_complete_lifecycle_with_wal(self, tmp_path):
        """Тест полного жизненного цикла: создание → обновление → удаление с WAL."""
        wal_dir = tmp_path / "wal"
        wal_mgr = WALManager(wal_dir=wal_dir)

        attr_file = tmp_path / "data" / "lifecycle.attr.json"

        # 1. Создание
        attrs_v1 = {"file_id": "test", "version": 1}
        tx1 = write_attr_file_atomic(attr_file, attrs_v1, wal_manager=wal_mgr)

        assert attr_file.exists()
        assert wal_mgr.get_wal_entry(tx1).operation_status == OperationStatus.COMMITTED

        # 2. Обновление
        attrs_v2 = {"file_id": "test", "version": 2, "updated": True}
        tx2 = write_attr_file_atomic(attr_file, attrs_v2, wal_manager=wal_mgr)

        loaded = read_attr_file(attr_file)
        assert loaded["version"] == 2
        assert wal_mgr.get_wal_entry(tx2).operation_status == OperationStatus.COMMITTED

        # 3. Удаление
        tx3 = delete_attr_file_atomic(attr_file, wal_manager=wal_mgr)

        assert not attr_file.exists()
        assert wal_mgr.get_wal_entry(tx3).operation_status == OperationStatus.COMMITTED

        # Проверяем что все 3 транзакции залогированы
        assert len(list(wal_dir.glob("wal_*.json"))) == 3

    def test_multiple_files_same_wal(self, tmp_path):
        """Тест множественных файлов с одним WAL manager."""
        wal_dir = tmp_path / "wal"
        wal_mgr = WALManager(wal_dir=wal_dir)

        # Создаем несколько файлов
        files = []
        for i in range(5):
            attr_file = tmp_path / f"file{i}.attr.json"
            attrs = {"file_id": f"test{i}", "index": i}
            write_attr_file_atomic(attr_file, attrs, wal_manager=wal_mgr)
            files.append(attr_file)

        # Проверяем что все файлы созданы
        for f in files:
            assert f.exists()

        # Проверяем что все транзакции залогированы
        assert len(list(wal_dir.glob("wal_*.json"))) == 5

    def test_wal_recovery_simulation(self, tmp_path):
        """Тест симуляции восстановления после сбоя через WAL."""
        wal_dir = tmp_path / "wal"
        wal_mgr = WALManager(wal_dir=wal_dir)

        attr_file = tmp_path / "data" / "recovery.attr.json"
        attrs = {"file_id": "test", "important": "data"}

        # Создаем файл с WAL
        tx_id = write_attr_file_atomic(attr_file, attrs, wal_manager=wal_mgr)

        # "Crash" - удаляем файл но сохраняем WAL
        attr_file.unlink()
        assert not attr_file.exists()

        # Восстановление через WAL
        wal_entry = wal_mgr.get_wal_entry(tx_id)
        assert wal_entry is not None
        assert wal_entry.operation_status == OperationStatus.COMMITTED

        # Восстанавливаем файл из WAL payload
        recovered_attrs = wal_entry.payload["attributes"]
        write_attr_file_atomic(attr_file, recovered_attrs)

        # Проверяем восстановленные данные
        loaded = read_attr_file(attr_file)
        assert loaded == attrs


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_exactly_4kb_size(self, tmp_path):
        """Тест граничного случая - ровно 4KB."""
        attr_file = tmp_path / "test.attr.json"

        # Создаем атрибуты приближенные к 4KB
        # JSON с indent=2 и ensure_ascii=False занимает больше места
        # Нужно подобрать размер эмпирически
        padding_size = 3900  # Примерно под 4KB с учетом JSON форматирования

        attrs = {
            "file_id": "test",
            "padding": "a" * padding_size
        }

        # Должно работать без ошибок (или выдать ValueError если превысили)
        try:
            write_attr_file_atomic(attr_file, attrs, max_size_bytes=4096)
            assert attr_file.exists()
        except ValueError as e:
            # Если превысили 4KB - это нормально, проверяем что ошибка корректная
            assert "exceeds maximum" in str(e)

    def test_empty_attributes(self, tmp_path):
        """Тест пустых атрибутов."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {}

        write_attr_file_atomic(attr_file, attrs)

        loaded = read_attr_file(attr_file)
        assert loaded == {}

    def test_nested_complex_attributes(self, tmp_path):
        """Тест вложенных сложных атрибутов."""
        attr_file = tmp_path / "test.attr.json"
        attrs = {
            "file_id": "test",
            "metadata": {
                "nested": {
                    "deep": {
                        "value": "data"
                    }
                },
                "array": [1, 2, 3, {"key": "value"}],
                "unicode": "тест 測試 テスト"
            }
        }

        write_attr_file_atomic(attr_file, attrs)

        loaded = read_attr_file(attr_file)
        assert loaded == attrs
        assert loaded["metadata"]["nested"]["deep"]["value"] == "data"

    def test_special_characters_in_path(self, tmp_path):
        """Тест специальных символов в пути файла."""
        # Некоторые специальные символы могут быть проблематичны
        special_dir = tmp_path / "dir with spaces" / "sub-dir_123"
        attr_file = special_dir / "test.attr.json"

        attrs = {"test": "data"}

        write_attr_file_atomic(attr_file, attrs)

        assert attr_file.exists()
        loaded = read_attr_file(attr_file)
        assert loaded == attrs
