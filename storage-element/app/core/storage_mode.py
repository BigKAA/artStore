"""
Storage mode state machine для Storage Element.

Реализует state transitions и validation для режимов:
- EDIT: Full CRUD (фиксированный режим)
- RW: Read-write без delete (может → RO)
- RO: Read-only (может → AR)
- AR: Archive mode (только через config)
"""

from enum import Enum
from typing import Optional, Set, Dict
from datetime import datetime, timezone

from app.core.logging import get_logger

logger = get_logger()


class StorageMode(str, Enum):
    """
    Storage Element operational modes.

    Modes:
    - EDIT: Full CRUD operations (create, read, update, delete)
    - RW: Read-write operations (no delete)
    - RO: Read-only operations
    - AR: Archive mode (metadata only, files on cold storage)
    """
    EDIT = "edit"
    RW = "rw"
    RO = "ro"
    AR = "ar"


class ModeTransitionError(Exception):
    """Raised when invalid mode transition is attempted."""
    pass


class StorageModeStateMachine:
    """
    State machine для Storage Element modes с transition validation.

    Transition Rules:
    - EDIT: Cannot transition (fixed mode)
    - RW → RO: Via API
    - RO → AR: Via API
    - AR → *: Only via config change + restart

    Features:
    - Transition validation
    - State history tracking
    - Transition logging
    - Read-only mode enforcement
    """

    # Valid transitions (from → to)
    VALID_TRANSITIONS: Dict[StorageMode, Set[StorageMode]] = {
        StorageMode.EDIT: set(),  # Cannot transition from EDIT
        StorageMode.RW: {StorageMode.RO},  # RW can only go to RO
        StorageMode.RO: {StorageMode.AR},  # RO can only go to AR
        StorageMode.AR: set(),  # Cannot transition from AR via API
    }

    # Operation permissions per mode
    OPERATIONS: Dict[StorageMode, Set[str]] = {
        StorageMode.EDIT: {"create", "read", "update", "delete"},
        StorageMode.RW: {"create", "read", "update"},
        StorageMode.RO: {"read"},
        StorageMode.AR: {"metadata"},  # Only metadata access
    }

    def __init__(self, current_mode: StorageMode):
        """
        Initialize state machine.

        Args:
            current_mode: Current storage mode
        """
        self.current_mode = current_mode
        self.logger = logger

        # Transition history
        self.transition_history: list = []

        self.logger.info(
            "Storage mode state machine initialized",
            mode=current_mode.value
        )

    def can_transition_to(self, target_mode: StorageMode) -> bool:
        """
        Check if transition to target mode is allowed.

        Args:
            target_mode: Desired mode

        Returns:
            bool: True if transition is allowed
        """
        return target_mode in self.VALID_TRANSITIONS.get(self.current_mode, set())

    def validate_transition(self, target_mode: StorageMode) -> None:
        """
        Validate mode transition.

        Args:
            target_mode: Desired mode

        Raises:
            ModeTransitionError: If transition is not allowed
        """
        if self.current_mode == target_mode:
            raise ModeTransitionError(
                f"Already in {target_mode.value} mode"
            )

        if not self.can_transition_to(target_mode):
            raise ModeTransitionError(
                f"Cannot transition from {self.current_mode.value} to {target_mode.value}. "
                f"Valid transitions from {self.current_mode.value}: "
                f"{[m.value for m in self.VALID_TRANSITIONS.get(self.current_mode, set())] or 'none'}"
            )

    def transition_to(self, target_mode: StorageMode, reason: Optional[str] = None) -> None:
        """
        Transition to new mode with validation.

        Args:
            target_mode: Desired mode
            reason: Optional reason for transition

        Raises:
            ModeTransitionError: If transition is invalid
        """
        # Validate transition
        self.validate_transition(target_mode)

        # Record transition
        transition_record = {
            "from_mode": self.current_mode.value,
            "to_mode": target_mode.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        }

        self.transition_history.append(transition_record)

        # Update mode
        old_mode = self.current_mode
        self.current_mode = target_mode

        self.logger.info(
            "Storage mode transition completed",
            from_mode=old_mode.value,
            to_mode=target_mode.value,
            reason=reason
        )

    def can_perform_operation(self, operation: str) -> bool:
        """
        Check if operation is allowed in current mode.

        Args:
            operation: Operation name (create, read, update, delete, metadata)

        Returns:
            bool: True if operation is allowed
        """
        allowed_operations = self.OPERATIONS.get(self.current_mode, set())
        return operation in allowed_operations

    def validate_operation(self, operation: str) -> None:
        """
        Validate operation is allowed in current mode.

        Args:
            operation: Operation name

        Raises:
            PermissionError: If operation is not allowed in current mode
        """
        if not self.can_perform_operation(operation):
            allowed_ops = self.OPERATIONS.get(self.current_mode, set())
            raise PermissionError(
                f"Operation '{operation}' not allowed in {self.current_mode.value} mode. "
                f"Allowed operations: {list(allowed_ops)}"
            )

    def get_allowed_operations(self) -> Set[str]:
        """
        Get set of allowed operations in current mode.

        Returns:
            Set[str]: Allowed operations
        """
        return self.OPERATIONS.get(self.current_mode, set()).copy()

    def get_possible_transitions(self) -> Set[StorageMode]:
        """
        Get set of modes that can be transitioned to from current mode.

        Returns:
            Set[StorageMode]: Possible target modes
        """
        return self.VALID_TRANSITIONS.get(self.current_mode, set()).copy()

    def get_transition_history(self) -> list:
        """
        Get transition history.

        Returns:
            list: List of transition records
        """
        return self.transition_history.copy()

    def get_mode_info(self) -> dict:
        """
        Get comprehensive info about current mode.

        Returns:
            dict: Mode information
        """
        return {
            "current_mode": self.current_mode.value,
            "allowed_operations": list(self.get_allowed_operations()),
            "possible_transitions": [m.value for m in self.get_possible_transitions()],
            "can_delete": self.can_perform_operation("delete"),
            "can_create": self.can_perform_operation("create"),
            "can_update": self.can_perform_operation("update"),
            "read_only": self.current_mode in {StorageMode.RO, StorageMode.AR},
            "is_archived": self.current_mode == StorageMode.AR
        }

    @classmethod
    def get_transition_matrix(cls) -> Dict[str, list]:
        """
        Get complete transition matrix for documentation.

        Returns:
            dict: Transition matrix
        """
        matrix = {}
        for mode in StorageMode:
            matrix[mode.value] = [
                target.value for target in cls.VALID_TRANSITIONS.get(mode, set())
            ]
        return matrix

    @classmethod
    def get_operation_matrix(cls) -> Dict[str, list]:
        """
        Get complete operation permissions matrix.

        Returns:
            dict: Operation permissions by mode
        """
        matrix = {}
        for mode in StorageMode:
            matrix[mode.value] = list(cls.OPERATIONS.get(mode, set()))
        return matrix
