from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import services
from app.api import deps
from app.db.models.user import User as DBUser
from app.models.user import User, UserCreate, UserUpdate
from app.db import session

router = APIRouter()


@router.get("/", response_model=List[User])
async def read_users(
    db: AsyncSession = Depends(session.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: DBUser = Depends(deps.get_current_active_admin),
) -> Any:
    """
    Retrieve users.
    """
    users = await services.user.get_multi(db, skip=skip, limit=limit)
    return users


@router.post("/", response_model=User)
async def create_user(
    *,
    db: AsyncSession = Depends(session.get_db),
    user_in: UserCreate,
    current_user: DBUser = Depends(deps.get_current_active_admin),
) -> Any:
    """
    Create new user.
    """
    user = await services.user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    user = await services.user.create(db, obj_in=user_in)
    return user


@router.get("/me", response_model=User)
async def read_users_me(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    return current_user


@router.get("/{user_id}", response_model=User)
async def read_user_by_id(
    user_id: int,
    current_user: DBUser = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(session.get_db),
) -> Any:
    """
    Get a specific user by id.
    """
    user = await services.user.get(db, id=user_id)
    if user == current_user or current_user.is_admin:
        return user
    raise HTTPException(
        status_code=403,
        detail="The user doesn't have enough privileges",
    )


@router.put("/{user_id}", response_model=User)
async def update_user(
    *,
    db: AsyncSession = Depends(session.get_db),
    user_id: int,
    user_in: UserUpdate,
    current_user: DBUser = Depends(deps.get_current_active_admin),
) -> Any:
    """
    Update a user.
    """
    user = await services.user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this username does not exist in the system",
        )
    user = await services.user.update(db, db_obj=user, obj_in=user_in)
    return user