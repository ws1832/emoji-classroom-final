"""课堂会话和排课 REST API。"""

from fastapi import APIRouter, Query

from app.controllers.session import session_controller
from app.core.ctx import CTX_USER_ID
from app.core.dependency import DependAuth
from app.models import User
from app.schemas.base import Success, SuccessExtra
from app.schemas.classroom import ClassSessionCreate, ClassSessionUpdate, ScheduleUserCreate
from app.services.ai_jobs import is_admin
from app.utils.time import format_beijing

router = APIRouter()


@router.get("/mine", dependencies=[DependAuth], summary="当前用户的排课")
async def my_sessions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    total, sessions = await session_controller.list_for_user(CTX_USER_ID.get(), page, page_size)
    data = []
    for session in sessions:
        item = await session.to_dict()
        course = await session.course
        item["course_name"] = course.name
        data.append(item)
    return SuccessExtra(data=data, total=total, page=page, page_size=page_size)


async def _dict(obj):
    return obj if isinstance(obj, dict) else await obj.to_dict()


@router.get("", response_model=None, dependencies=[DependAuth], summary="查询课堂会话")
async def list_sessions(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), course_id: int | None = None
):
    actor_id = CTX_USER_ID.get()
    actor = await User.get(id=actor_id)
    if await is_admin(actor):
        total, sessions = await session_controller.list(page, page_size)
    else:
        total, sessions = await session_controller.list_for_teacher(actor_id, page, page_size, course_id)
    return SuccessExtra(data=[await _dict(item) for item in sessions], total=total, page=page, page_size=page_size)


@router.post("", response_model=None, dependencies=[DependAuth], summary="创建课堂会话")
async def create_session(payload: ClassSessionCreate):
    item = await session_controller.create_session(payload, actor_id=CTX_USER_ID.get())
    return Success(data=await _dict(item))


@router.put("/{session_id}", response_model=None, dependencies=[DependAuth], summary="更新课堂会话")
async def update_session(session_id: int, payload: ClassSessionUpdate):
    item = await session_controller.update_session(
        payload.model_copy(update={"id": session_id}), actor_id=CTX_USER_ID.get()
    )
    return Success(data=await _dict(item))


@router.delete("/{session_id}", response_model=None, dependencies=[DependAuth], summary="删除课堂会话")
async def delete_session(session_id: int):
    await session_controller.delete_session(session_id, actor_id=CTX_USER_ID.get())
    return Success(msg="Deleted Successfully")


@router.get("/{session_id}/schedule", response_model=None, dependencies=[DependAuth], summary="查询课堂已安排用户")
async def list_scheduled_users(session_id: int):
    schedules = await session_controller.list_scheduled_users(session_id, CTX_USER_ID.get())
    data = []
    for schedule in schedules:
        data.append(
            {
                "id": schedule.id,
                "user_id": schedule.user_id,
                "username": schedule.user.username if schedule.user else None,
                "scheduled_at": format_beijing(schedule.scheduled_at, "%Y-%m-%d %H:%M:%S") if schedule.scheduled_at else None,
            }
        )
    return Success(data=data)


@router.post("/{session_id}/schedule", response_model=None, dependencies=[DependAuth], summary="安排课堂用户")
async def schedule_user(session_id: int, payload: ScheduleUserCreate):
    item = await session_controller.schedule_user(
        payload.model_copy(update={"session_id": session_id}), actor_id=CTX_USER_ID.get()
    )
    return Success(data=await _dict(item))


@router.delete(
    "/{session_id}/schedule/{user_id}", response_model=None, dependencies=[DependAuth], summary="取消课堂用户安排"
)
async def unschedule_user(session_id: int, user_id: int):
    await session_controller.unschedule_user(session_id, user_id, actor_id=CTX_USER_ID.get())
    return Success(msg="Deleted Successfully")
