from pydantic import BaseModel, EmailStr
from typing import Optional
import datetime

# --- Схемы для групп ---
class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None

class GroupCreate(GroupBase):
    pass

class GroupUpdate(GroupBase):
    pass

class GroupInDBBase(GroupBase):
    id: int

    model_config = {"from_attributes": True}

class Group(GroupInDBBase):
    pass

# --- Схемы для пользователей ---
class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class UserInDBBase(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    groups: list[Group] = []

    model_config = {"from_attributes": True}

class User(UserInDBBase):
    pass

class UserInDB(UserInDBBase):
    hashed_password: str