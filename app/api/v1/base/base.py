from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from tortoise.transactions import in_transaction
from app.models import Course, ScheduleUser

from app.controllers.user import user_controller
from app.core.ctx import CTX_USER_ID
from app.core.dependency import DependAuth
from app.models.admin import Api, Menu, Role, User
from app.schemas.base import Fail, Success
from app.schemas.login import *
from app.schemas.users import UpdatePassword
from app.settings import settings
from app.utils.jwt_utils import create_access_token, credential_tag
from app.utils.password import get_password_hash, is_password_strong, verify_password

router = APIRouter()


class StudentRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=20, pattern=r"^\S+$")
    email: EmailStr
    password: str = Field(max_length=128, description="密码")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not is_password_strong(value):
            raise ValueError("密码须为 8~128 位，且同时包含字母和数字")
        return value


class TeacherRegister(StudentRegister):
    """教师注册请求结构与学生一致，服务端固定为教师角色。"""


async def _register(payload: StudentRegister, role_name: str, role_desc: str) -> User:
    async with in_transaction():
        if (
            await User.filter(username=payload.username).exists()
            or await User.filter(email=str(payload.email)).exists()
        ):
            raise HTTPException(409, "用户名或邮箱已存在")
        user = await User.create(
            username=payload.username,
            email=str(payload.email),
            password=get_password_hash(payload.password),
            user_no=await User.next_user_no(role_name),
            is_active=True,
            is_superuser=False,
        )
        role, _ = await Role.get_or_create(name=role_name, defaults={"desc": role_desc})
        await user.roles.add(role)
        return user


@router.post("/register", summary="注册学生")
async def register_student(payload: StudentRegister):
    user = await _register(payload, "STUDENT", "学生角色")
    return Success(data={"id": user.id, "username": user.username, "user_no": user.user_no})


@router.post("/register-teacher", summary="注册教师")
async def register_teacher(payload: TeacherRegister):
    user = await _register(payload, "TEACHER", "教师角色")
    return Success(data={"id": user.id, "username": user.username, "user_no": user.user_no})


@router.post("/access_token", summary="获取token")
async def login_access_token(credentials: CredentialsSchema):
    user: User = await user_controller.authenticate(credentials)
    await user_controller.update_last_login(user.id)
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + access_token_expires

    data = JWTOut(
        access_token=create_access_token(
            data=JWTPayload(
                user_id=user.id,
                username=user.username,
                is_superuser=user.is_superuser,
                exp=expire,
                credential_tag=credential_tag(user.password),
            )
        ),
        username=user.username,
    )
    return Success(data=data.model_dump())


@router.get("/userinfo", summary="查看用户信息", dependencies=[DependAuth])
async def get_userinfo():
    user_id = CTX_USER_ID.get()
    user_obj = await user_controller.get(id=user_id)
    data = await user_obj.to_dict(exclude_fields=["password"])
    data["avatar"] = "https://avatars.githubusercontent.com/u/54677442?v=4"
    # Stable server-derived capabilities; legacy course/schedule ownership remains valid.
    names = await user_obj.roles.all().values_list("name", flat=True)
    data["is_admin"] = user_obj.is_superuser or "ADMIN" in names
    codes = [code for code in ["STUDENT", "TEACHER"] if code in names]
    if await Course.filter(teacher_id=user_id).exists() and "TEACHER" not in codes:
        codes.append("TEACHER")
    if await ScheduleUser.filter(user_id=user_id).exists() and "STUDENT" not in codes:
        codes.append("STUDENT")
    data["role_codes"] = codes
    return Success(data=data)


@router.get("/usermenu", summary="查看用户菜单", dependencies=[DependAuth])
async def get_user_menu():
    user_id = CTX_USER_ID.get()
    user_obj = await User.filter(id=user_id).first()
    menus: list[Menu] = []
    if user_obj.is_superuser:
        menus = await Menu.all()
    else:
        role_objs: list[Role] = await user_obj.roles
        for role_obj in role_objs:
            menu = await role_obj.menus
            menus.extend(menu)
        menus = list(set(menus))
    parent_menus: list[Menu] = []
    for menu in menus:
        if menu.parent_id == 0:
            parent_menus.append(menu)
    res = []
    for parent_menu in parent_menus:
        parent_menu_dict = await parent_menu.to_dict()
        parent_menu_dict["children"] = []
        for menu in menus:
            if menu.parent_id == parent_menu.id:
                parent_menu_dict["children"].append(await menu.to_dict())
        res.append(parent_menu_dict)
    return Success(data=res)


@router.get("/userapi", summary="查看用户API", dependencies=[DependAuth])
async def get_user_api():
    user_id = CTX_USER_ID.get()
    user_obj = await User.filter(id=user_id).first()
    if user_obj.is_superuser:
        api_objs: list[Api] = await Api.all()
        apis = [api.method.lower() + api.path for api in api_objs]
        return Success(data=apis)
    role_objs: list[Role] = await user_obj.roles
    apis = []
    for role_obj in role_objs:
        api_objs: list[Api] = await role_obj.apis
        apis.extend([api.method.lower() + api.path for api in api_objs])
    apis = list(set(apis))
    return Success(data=apis)


@router.post("/update_password", summary="修改密码", dependencies=[DependAuth])
async def update_user_password(req_in: UpdatePassword):
    user_id = CTX_USER_ID.get()
    user = await user_controller.get(user_id)
    verified = verify_password(req_in.old_password, user.password)
    if not verified:
        return Fail(msg="旧密码验证错误！")
    await user_controller.set_password(user, req_in.new_password)
    return Success(msg="修改成功")
