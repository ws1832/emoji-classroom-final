"""课程 REST API。"""

from fastapi import APIRouter, Query

from app.controllers.course import course_controller
from app.core.ctx import CTX_USER_ID
from app.core.dependency import DependAuth
from app.models import User
from app.schemas.base import Success, SuccessExtra
from app.schemas.classroom import CourseCreate, CourseUpdate
from app.services.ai_jobs import is_admin

router = APIRouter()


async def _dict(obj):
    return obj if isinstance(obj, dict) else await obj.to_dict()


@router.get("", response_model=None, dependencies=[DependAuth], summary="查询课程")
async def list_courses(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = ""):
    actor_id = CTX_USER_ID.get()
    actor = await User.get(id=actor_id)
    if await is_admin(actor):
        total, courses = await course_controller.list(page, page_size)
    else:
        total, courses = await course_controller.list_for_teacher(actor_id, page, page_size, keyword)
    return SuccessExtra(data=[await _dict(item) for item in courses], total=total, page=page, page_size=page_size)


@router.post("", response_model=None, dependencies=[DependAuth], summary="创建课程")
async def create_course(payload: CourseCreate):
    item = await course_controller.create_course(payload, actor_id=CTX_USER_ID.get())
    return Success(data=await _dict(item))


@router.put("/{course_id}", response_model=None, dependencies=[DependAuth], summary="更新课程")
async def update_course(course_id: int, payload: CourseUpdate):
    item = await course_controller.update_course(payload.model_copy(update={"id": course_id}), actor_id=CTX_USER_ID.get())
    return Success(data=await _dict(item))


@router.delete("/{course_id}", response_model=None, dependencies=[DependAuth], summary="删除课程")
async def delete_course(course_id: int):
    await course_controller.delete_course(course_id, actor_id=CTX_USER_ID.get())
    return Success(msg="Deleted Successfully")
