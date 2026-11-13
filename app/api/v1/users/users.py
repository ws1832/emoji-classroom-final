import logging

from fastapi import APIRouter, Body, Query, Depends, HTTPException
from tortoise.expressions import Q

from app.controllers.user import user_controller
from app.schemas.base import Fail, Success, SuccessExtra
from app.schemas.users import *
from app.core.dependency import require_admin_user
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin_user)])


async def protect_superuser(actor, target=None, requested=False):
    if not actor.is_superuser and (requested or (target and target.is_superuser)):
        raise HTTPException(403, "仅超级管理员可修改超级用户")


@router.get("/list", summary="查看用户列表")
async def list_user(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=1000, description="每页数量"),
    username: str = Query("", description="用户名称，用于搜索"),
    email: str = Query("", description="邮箱地址"),
):
    q = Q()
    if username:
        q &= Q(username__contains=username)
    if email:
        q &= Q(email__contains=email)
    total, user_objs = await user_controller.list(page=page, page_size=page_size, search=q)
    data = [await obj.to_dict(m2m=True, exclude_fields=["password"]) for obj in user_objs]

    return SuccessExtra(data=data, total=total, page=page, page_size=page_size)


@router.get("/get", summary="查看用户")
async def get_user(
    user_id: int = Query(..., description="用户ID"),
):
    user_obj = await user_controller.get(id=user_id)
    user_dict = await user_obj.to_dict(exclude_fields=["password"])
    return Success(data=user_dict)


@router.post("/create", summary="创建用户")
async def create_user(
    user_in: UserCreate,
    actor: User = Depends(require_admin_user),
):
    await protect_superuser(actor, requested=user_in.is_superuser)
    user = await user_controller.get_by_email(user_in.email)
    if user:
        return Fail(code=400, msg="The user with this email already exists in the system.")
    new_user = await user_controller.create_user(obj_in=user_in)
    await user_controller.update_roles(new_user, user_in.role_ids)
    return Success(msg="Created Successfully")


@router.post("/update", summary="更新用户")
async def update_user(
    user_in: UserUpdate,
    actor: User = Depends(require_admin_user),
):
    target = await user_controller.get(id=user_in.id)
    await protect_superuser(actor, target, user_in.is_superuser)
    if actor.id == target.id and not user_in.is_active:
        raise HTTPException(403, "不能禁用当前登录用户")
    user = await user_controller.update(id=user_in.id, obj_in=user_in)
    await user_controller.update_roles(user, user_in.role_ids)
    return Success(msg="Updated Successfully")


@router.delete("/delete", summary="删除用户")
async def delete_user(
    user_id: int = Query(..., description="用户ID"),
    actor: User = Depends(require_admin_user),
):
    target = await user_controller.get(id=user_id)
    await protect_superuser(actor, target)
    if actor.id == target.id:
        raise HTTPException(403, "不能删除当前登录用户")
    await user_controller.remove(id=user_id)
    return Success(msg="Deleted Successfully")


@router.post("/reset_password", summary="重置密码")
async def reset_password(user_id: int = Body(..., description="用户ID", embed=True)):
    password = await user_controller.reset_password(user_id)
    return Success(
        data={"temporary_password": password},
        msg="随机密码仅显示一次，请交付用户并尽快修改",
        headers={"Cache-Control": "no-store"},
    )
