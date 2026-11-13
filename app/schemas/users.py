from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.password import is_password_strong


class BaseUser(BaseModel):
    id: int
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    last_login: Optional[datetime]
    roles: Optional[list] = []


class UserCreate(BaseModel):
    email: EmailStr = Field(example="admin@qq.com")
    username: str = Field(min_length=1, max_length=20, pattern=r"^\S+$", example="admin")
    password: str = Field(max_length=128, example="ExamplePass123")
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False
    role_ids: Optional[List[int]] = []
    dept_id: Optional[int] = Field(0, description="部门ID")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not is_password_strong(value):
            raise ValueError("密码须为 8~128 位，且同时包含字母和数字")
        return value

    def create_dict(self):
        return self.model_dump(exclude_unset=True, exclude={"role_ids"})


class UserUpdate(BaseModel):
    id: int
    email: EmailStr
    username: str = Field(min_length=1, max_length=20, pattern=r"^\S+$")
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False
    role_ids: Optional[List[int]] = []
    dept_id: Optional[int] = 0


class UpdatePassword(BaseModel):
    old_password: str = Field(max_length=128, description="旧密码")
    new_password: str = Field(max_length=128, description="新密码")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not is_password_strong(value):
            raise ValueError("密码须为 8~128 位，且同时包含字母和数字")
        return value
