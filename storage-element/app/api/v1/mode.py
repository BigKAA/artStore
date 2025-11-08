"""
Storage mode management API endpoints.

Endpoints для управления режимами работы Storage Element.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional

from app.core.storage_mode import (
    StorageMode,
    StorageModeStateMachine,
    ModeTransitionError
)
from app.core.auth import User, Permission
from app.api.dependencies import (
    get_current_user,
    require_permission,
    require_operator_or_admin,
)
from app.core.config import get_config
from app.core.logging import get_logger

# Router configuration
router = APIRouter()
logger = get_logger()
config = get_config()

# Global state machine instance (singleton pattern)
_state_machine: Optional[StorageModeStateMachine] = None


def get_state_machine() -> StorageModeStateMachine:
    """
    Get or create global state machine instance.

    Returns:
        StorageModeStateMachine: Global state machine
    """
    global _state_machine

    if _state_machine is None:
        # Initialize from config
        initial_mode = StorageMode(config.mode.mode)
        _state_machine = StorageModeStateMachine(current_mode=initial_mode)

    return _state_machine


class ModeTransitionRequest(BaseModel):
    """Request model for mode transition."""
    target_mode: StorageMode
    reason: Optional[str] = None


class ModeInfoResponse(BaseModel):
    """Response model for mode information."""
    current_mode: str
    allowed_operations: list[str]
    possible_transitions: list[str]
    can_delete: bool
    can_create: bool
    can_update: bool
    read_only: bool
    is_archived: bool


@router.get(
    "/info",
    response_model=ModeInfoResponse,
    summary="Get current mode information",
    description="Get comprehensive information about current storage mode",
    dependencies=[Depends(require_permission(Permission.MODE_READ))]
)
async def get_mode_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current mode information.

    Returns:
        ModeInfoResponse: Current mode details and permissions

    Example Response:
        {
          "current_mode": "rw",
          "allowed_operations": ["create", "read", "update"],
          "possible_transitions": ["ro"],
          "can_delete": false,
          "can_create": true,
          "can_update": true,
          "read_only": false,
          "is_archived": false
        }
    """
    state_machine = get_state_machine()
    info = state_machine.get_mode_info()

    logger.info(
        "Mode info requested",
        mode=info["current_mode"],
        user=current_user.username,
        user_id=current_user.user_id
    )

    return ModeInfoResponse(**info)


@router.post(
    "/transition",
    status_code=status.HTTP_200_OK,
    summary="Transition to new mode",
    description="Transition storage element to a new operational mode"
)
async def transition_mode(
    request: ModeTransitionRequest,
    current_user: User = Depends(require_operator_or_admin)
):
    """
    Transition to new storage mode.

    Valid transitions:
    - RW → RO
    - RO → AR

    Invalid transitions:
    - EDIT → * (EDIT mode is fixed)
    - AR → * (Archive mode requires config change + restart)

    Args:
        request: Transition request with target mode and optional reason

    Returns:
        dict: Transition result with new mode information

    Raises:
        HTTPException 400: Invalid transition
        HTTPException 409: Already in target mode

    Example Request:
        {
          "target_mode": "ro",
          "reason": "Storage element full, switching to read-only"
        }

    Example Response:
        {
          "success": true,
          "from_mode": "rw",
          "to_mode": "ro",
          "message": "Successfully transitioned to ro mode",
          "current_mode_info": {...}
        }
    """
    state_machine = get_state_machine()

    logger.info(
        "Mode transition requested",
        from_mode=state_machine.current_mode.value,
        to_mode=request.target_mode.value,
        reason=request.reason,
        user=current_user.username,
        user_id=current_user.user_id,
        roles=[r.value for r in current_user.roles]
    )

    try:
        # Attempt transition
        state_machine.transition_to(
            target_mode=request.target_mode,
            reason=request.reason
        )

        # Get updated mode info
        mode_info = state_machine.get_mode_info()

        return {
            "success": True,
            "from_mode": state_machine.transition_history[-1]["from_mode"],
            "to_mode": request.target_mode.value,
            "message": f"Successfully transitioned to {request.target_mode.value} mode",
            "current_mode_info": mode_info
        }

    except ModeTransitionError as e:
        logger.warning(
            "Invalid mode transition attempt",
            from_mode=state_machine.current_mode.value,
            to_mode=request.target_mode.value,
            error=str(e)
        )

        # Check if already in target mode
        if state_machine.current_mode == request.target_mode:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )

        # Invalid transition
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/history",
    summary="Get mode transition history",
    description="Get history of all mode transitions",
    dependencies=[Depends(require_permission(Permission.MODE_READ))]
)
async def get_transition_history(
    current_user: User = Depends(get_current_user)
):
    """
    Get mode transition history.

    Returns:
        dict: Transition history

    Example Response:
        {
          "transitions": [
            {
              "from_mode": "rw",
              "to_mode": "ro",
              "timestamp": "2024-01-15T10:30:00Z",
              "reason": "Storage full"
            }
          ],
          "count": 1
        }
    """
    state_machine = get_state_machine()
    history = state_machine.get_transition_history()

    logger.info("Transition history requested", count=len(history))

    return {
        "transitions": history,
        "count": len(history)
    }


@router.get(
    "/matrix",
    summary="Get transition and operation matrices",
    description="Get complete transition rules and operation permissions",
    dependencies=[Depends(require_permission(Permission.MODE_READ))]
)
async def get_mode_matrices(
    current_user: User = Depends(get_current_user)
):
    """
    Get transition matrix and operation permissions.

    Returns:
        dict: Complete mode system information

    Example Response:
        {
          "transition_matrix": {
            "edit": [],
            "rw": ["ro"],
            "ro": ["ar"],
            "ar": []
          },
          "operation_matrix": {
            "edit": ["create", "read", "update", "delete"],
            "rw": ["create", "read", "update"],
            "ro": ["read"],
            "ar": ["metadata"]
          }
        }
    """
    transition_matrix = StorageModeStateMachine.get_transition_matrix()
    operation_matrix = StorageModeStateMachine.get_operation_matrix()

    return {
        "transition_matrix": transition_matrix,
        "operation_matrix": operation_matrix
    }


@router.post(
    "/validate",
    summary="Validate operation in current mode",
    description="Check if operation is allowed in current mode",
    dependencies=[Depends(require_permission(Permission.MODE_READ))]
)
async def validate_operation(
    operation: str,
    current_user: User = Depends(get_current_user)
):
    """
    Validate if operation is allowed in current mode.

    Args:
        operation: Operation to validate (create, read, update, delete, metadata)

    Returns:
        dict: Validation result

    Example Request:
        POST /api/v1/mode/validate?operation=delete

    Example Response:
        {
          "operation": "delete",
          "allowed": false,
          "current_mode": "rw",
          "reason": "Delete operation not allowed in rw mode"
        }
    """
    state_machine = get_state_machine()

    is_allowed = state_machine.can_perform_operation(operation)

    result = {
        "operation": operation,
        "allowed": is_allowed,
        "current_mode": state_machine.current_mode.value
    }

    if not is_allowed:
        allowed_ops = list(state_machine.get_allowed_operations())
        result["reason"] = (
            f"{operation.capitalize()} operation not allowed in "
            f"{state_machine.current_mode.value} mode"
        )
        result["allowed_operations"] = allowed_ops

    logger.info(
        "Operation validation",
        operation=operation,
        mode=state_machine.current_mode.value,
        allowed=is_allowed
    )

    return result
