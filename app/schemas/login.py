from datetime import datetime

from pydantic import BaseModel, Field


class CredentialsSchema(BaseModel):
    username: str = Field(..., min_length=1, max_length=20, description="用户名称", example="admin")
    password: str = Field(..., min_length=1, max_length=128, description="密码", example="ExamplePass123")


class JWTOut(BaseModel):
    access_token: str
    username: str


class JWTPayload(BaseModel):
    user_id: int
    username: str
    is_superuser: bool
    exp: datetime
    credential_tag: str | None = None
