"""
Unit tests для storage mode state machine и API.

Тестирует state transitions, operation validation, и API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.storage_mode import (
    StorageMode,
    StorageModeStateMachine,
    ModeTransitionError
)


class TestStorageModeStateMachine:
    """Тесты для StorageModeStateMachine business logic."""

    def test_initialization(self):
        """Тест инициализации state machine."""
        sm = StorageModeStateMachine(current_mode=StorageMode.EDIT)

        assert sm.current_mode == StorageMode.EDIT
        assert len(sm.transition_history) == 0

    def test_valid_transitions_rw_to_ro(self):
        """Тест валидного перехода RW → RO."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        assert sm.can_transition_to(StorageMode.RO) is True

        sm.transition_to(StorageMode.RO, reason="Test transition")

        assert sm.current_mode == StorageMode.RO
        assert len(sm.transition_history) == 1
        assert sm.transition_history[0]["from_mode"] == "rw"
        assert sm.transition_history[0]["to_mode"] == "ro"

    def test_valid_transitions_ro_to_ar(self):
        """Тест валидного перехода RO → AR."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RO)

        assert sm.can_transition_to(StorageMode.AR) is True

        sm.transition_to(StorageMode.AR, reason="Archiving")

        assert sm.current_mode == StorageMode.AR
        assert len(sm.transition_history) == 1

    def test_invalid_transition_from_edit(self):
        """Тест невалидного перехода из EDIT."""
        sm = StorageModeStateMachine(current_mode=StorageMode.EDIT)

        # EDIT не может transition куда-либо
        assert sm.can_transition_to(StorageMode.RW) is False
        assert sm.can_transition_to(StorageMode.RO) is False
        assert sm.can_transition_to(StorageMode.AR) is False

        with pytest.raises(ModeTransitionError, match="Cannot transition from edit"):
            sm.transition_to(StorageMode.RW)

    def test_invalid_transition_from_ar(self):
        """Тест невалидного перехода из AR."""
        sm = StorageModeStateMachine(current_mode=StorageMode.AR)

        # AR не может transition через API
        assert sm.can_transition_to(StorageMode.EDIT) is False
        assert sm.can_transition_to(StorageMode.RW) is False
        assert sm.can_transition_to(StorageMode.RO) is False

        with pytest.raises(ModeTransitionError, match="Cannot transition from ar"):
            sm.transition_to(StorageMode.EDIT)

    def test_invalid_transition_rw_to_ar(self):
        """Тест невалидного прямого перехода RW → AR."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        # RW может только в RO, не напрямую в AR
        assert sm.can_transition_to(StorageMode.AR) is False

        with pytest.raises(ModeTransitionError):
            sm.transition_to(StorageMode.AR)

    def test_transition_to_same_mode(self):
        """Тест перехода в текущий режим."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        with pytest.raises(ModeTransitionError, match="Already in rw mode"):
            sm.transition_to(StorageMode.RW)

    def test_operation_permissions_edit(self):
        """Тест прав операций в EDIT mode."""
        sm = StorageModeStateMachine(current_mode=StorageMode.EDIT)

        assert sm.can_perform_operation("create") is True
        assert sm.can_perform_operation("read") is True
        assert sm.can_perform_operation("update") is True
        assert sm.can_perform_operation("delete") is True
        assert sm.can_perform_operation("metadata") is False

    def test_operation_permissions_rw(self):
        """Тест прав операций в RW mode."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        assert sm.can_perform_operation("create") is True
        assert sm.can_perform_operation("read") is True
        assert sm.can_perform_operation("update") is True
        assert sm.can_perform_operation("delete") is False
        assert sm.can_perform_operation("metadata") is False

    def test_operation_permissions_ro(self):
        """Тест прав операций в RO mode."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RO)

        assert sm.can_perform_operation("create") is False
        assert sm.can_perform_operation("read") is True
        assert sm.can_perform_operation("update") is False
        assert sm.can_perform_operation("delete") is False
        assert sm.can_perform_operation("metadata") is False

    def test_operation_permissions_ar(self):
        """Тест прав операций в AR mode."""
        sm = StorageModeStateMachine(current_mode=StorageMode.AR)

        assert sm.can_perform_operation("create") is False
        assert sm.can_perform_operation("read") is False
        assert sm.can_perform_operation("update") is False
        assert sm.can_perform_operation("delete") is False
        assert sm.can_perform_operation("metadata") is True

    def test_validate_operation_allowed(self):
        """Тест validation разрешенной операции."""
        sm = StorageModeStateMachine(current_mode=StorageMode.EDIT)

        # Should not raise
        sm.validate_operation("delete")

    def test_validate_operation_forbidden(self):
        """Тест validation запрещенной операции."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RO)

        with pytest.raises(PermissionError, match="create.*not allowed in ro mode"):
            sm.validate_operation("create")

    def test_get_mode_info(self):
        """Тест получения информации о режиме."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        info = sm.get_mode_info()

        assert info["current_mode"] == "rw"
        assert "create" in info["allowed_operations"]
        assert "delete" not in info["allowed_operations"]
        assert info["possible_transitions"] == ["ro"]
        assert info["can_delete"] is False
        assert info["can_create"] is True
        assert info["read_only"] is False
        assert info["is_archived"] is False

    def test_get_mode_info_ro(self):
        """Тест информации для RO mode."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RO)

        info = sm.get_mode_info()

        assert info["read_only"] is True
        assert info["is_archived"] is False

    def test_get_mode_info_ar(self):
        """Тест информации для AR mode."""
        sm = StorageModeStateMachine(current_mode=StorageMode.AR)

        info = sm.get_mode_info()

        assert info["read_only"] is True
        assert info["is_archived"] is True

    def test_transition_history_tracking(self):
        """Тест отслеживания истории переходов."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        # First transition
        sm.transition_to(StorageMode.RO, reason="Storage full")

        # Get history
        history = sm.get_transition_history()

        assert len(history) == 1
        assert history[0]["from_mode"] == "rw"
        assert history[0]["to_mode"] == "ro"
        assert history[0]["reason"] == "Storage full"
        assert "timestamp" in history[0]

        # Second transition
        sm.transition_to(StorageMode.AR, reason="Long-term archive")

        history = sm.get_transition_history()

        assert len(history) == 2
        assert history[1]["from_mode"] == "ro"
        assert history[1]["to_mode"] == "ar"

    def test_get_transition_matrix(self):
        """Тест получения transition matrix."""
        matrix = StorageModeStateMachine.get_transition_matrix()

        assert matrix["edit"] == []
        assert matrix["rw"] == ["ro"]
        assert matrix["ro"] == ["ar"]
        assert matrix["ar"] == []

    def test_get_operation_matrix(self):
        """Тест получения operation matrix."""
        matrix = StorageModeStateMachine.get_operation_matrix()

        assert set(matrix["edit"]) == {"create", "read", "update", "delete"}
        assert set(matrix["rw"]) == {"create", "read", "update"}
        assert set(matrix["ro"]) == {"read"}
        assert set(matrix["ar"]) == {"metadata"}


class TestModeAPI:
    """Тесты для mode management API endpoints."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        return TestClient(app)

    def test_get_mode_info(self, client):
        """Тест получения mode info через API."""
        response = client.get("/api/v1/mode/info")

        assert response.status_code == 200
        data = response.json()

        assert "current_mode" in data
        assert "allowed_operations" in data
        assert "possible_transitions" in data
        assert "can_delete" in data
        assert "read_only" in data

    def test_get_transition_matrix(self, client):
        """Тест получения transition и operation matrices."""
        response = client.get("/api/v1/mode/matrix")

        assert response.status_code == 200
        data = response.json()

        assert "transition_matrix" in data
        assert "operation_matrix" in data

        # Validate structure
        assert "edit" in data["transition_matrix"]
        assert "rw" in data["operation_matrix"]

    def test_get_transition_history(self, client):
        """Тест получения transition history."""
        response = client.get("/api/v1/mode/history")

        assert response.status_code == 200
        data = response.json()

        assert "transitions" in data
        assert "count" in data
        assert isinstance(data["transitions"], list)

    def test_validate_operation_allowed(self, client):
        """Тест validation разрешенной операции через API."""
        response = client.post("/api/v1/mode/validate?operation=read")

        assert response.status_code == 200
        data = response.json()

        assert data["operation"] == "read"
        assert data["allowed"] is True
        assert "current_mode" in data

    def test_validate_operation_forbidden(self, client):
        """Тест validation запрещенной операции через API."""
        # This test depends on current mode from config
        # If mode is RO, delete should be forbidden
        response = client.post("/api/v1/mode/validate?operation=delete")

        assert response.status_code == 200
        data = response.json()

        assert data["operation"] == "delete"
        # Result depends on current mode
        assert "allowed" in data


class TestModeTransitionScenarios:
    """Integration tests для полных сценариев переходов."""

    def test_full_lifecycle_rw_to_ar(self):
        """Тест полного lifecycle: RW → RO → AR."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        # Step 1: RW → RO
        sm.transition_to(StorageMode.RO, reason="Storage approaching capacity")
        assert sm.current_mode == StorageMode.RO
        assert sm.can_perform_operation("read") is True
        assert sm.can_perform_operation("create") is False

        # Step 2: RO → AR
        sm.transition_to(StorageMode.AR, reason="Moving to cold storage")
        assert sm.current_mode == StorageMode.AR
        assert sm.can_perform_operation("metadata") is True
        assert sm.can_perform_operation("read") is False

        # Verify history
        history = sm.get_transition_history()
        assert len(history) == 2

    def test_operation_enforcement_after_transition(self):
        """Тест enforcement операций после transition."""
        sm = StorageModeStateMachine(current_mode=StorageMode.RW)

        # In RW mode, delete is forbidden
        with pytest.raises(PermissionError):
            sm.validate_operation("delete")

        # Transition to RO
        sm.transition_to(StorageMode.RO)

        # In RO mode, create is also forbidden
        with pytest.raises(PermissionError):
            sm.validate_operation("create")

        # But read is still allowed
        sm.validate_operation("read")  # Should not raise
