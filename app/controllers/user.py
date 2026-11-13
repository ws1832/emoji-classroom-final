from typing import List, Optional
import secrets

from fastapi.exceptions import HTTPException

from app.core.crud import CRUDBase
from app.models.admin import User
from app.schemas.login import CredentialsSchema
from app.schemas.users import UserCreate, UserUpdate
from app.utils.password import get_password_hash, verify_password
from app.utils.time import beijing_now
from tortoise.transactions import in_transaction

from .role import role_controller


class UserController(CRUDBase[User, UserCreate, UserUpdate]):
    def __init__(self):
        super().__init__(model=User)

    async def get_by_email(self, email: str) -> Optional[User]:
        return await self.model.filter(email=email).first()

    async def get_by_username(self, username: str) -> Optional[User]:
        return await self.model.filter(username=username).first()

    async def create_user(self, obj_in: UserCreate) -> User:
        obj_in.password = get_password_hash(password=obj_in.password)
        obj = await self.create(obj_in)
        return obj

    async def update_last_login(self, id: int) -> None:
        user = await self.model.get(id=id)
        user.last_login = beijing_now()
        await user.save()

    async def authenticate(self, credentials: CredentialsSchema) -> Optional["User"]:
        user = await self.model.filter(username=credentials.username).first()
        if not user:
            raise HTTPException(status_code=400, detail="无效的用户名")
        verified = verify_password(credentials.password, user.password)
        if not verified:
            raise HTTPException(status_code=400, detail="密码错误!")
        if not user.is_active:
            raise HTTPException(status_code=400, detail="用户已被禁用")
        return user

    async def update_roles(self, user: User, role_ids: List[int]) -> None:
        await user.roles.clear()
        for role_id in role_ids:
            role_obj = await role_controller.get(id=role_id)
            await user.roles.add(role_obj)

    async def set_password(self, user: User, password: str):
        from app.models.ai import BrowserCapture
        from app.core.ai_auth import utc_now, wall

        async with in_transaction() as db:
            user.password = get_password_hash(password=password)
            await user.save(using_db=db, update_fields=["password", "updated_at"])
            await BrowserCapture.filter(owner_id=user.id).using_db(db).update(
                active_key=None, owner_id=None, token_hash="", stopped_at=wall(utc_now())
            )

    async def reset_password(self, user_id: int):
        user_obj = await self.get(id=user_id)
        if user_obj.is_superuser:
            raise HTTPException(status_code=403, detail="不允许重置超级管理员密码")
        password = "R9-" + secrets.token_urlsafe(24)
        await self.set_password(user_obj, password)
        return password


user_controller = UserController()
