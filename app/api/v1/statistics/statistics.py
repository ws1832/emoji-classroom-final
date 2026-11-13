"""按课程、班级、时间段统计 REST API。"""

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.core.ctx import CTX_USER_ID
from app.core.dependency import DependAuth
from app.models import Course, User
from app.schemas.base import Success
from app.services.statistics import get_statistics
from app.services.ai_jobs import is_admin

router = APIRouter()


async def _require_teacher_or_admin(actor: User) -> None:
    if await is_admin(actor):
        return
    has_course = await Course.filter(teacher_id=actor.id).exists()
    if not has_course:
        raise HTTPException(status_code=403, detail="Only teachers and administrators can view statistics")


@router.get("", response_model=None, dependencies=[DependAuth], summary="多维统计")
async def statistics(
    course_id: int | None = None,
    class_name: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
):
    if any(value is not None and value.utcoffset() is not None for value in (from_time, to_time)):
        raise HTTPException(422, "Use Shanghai local time without a timezone offset")
    if from_time is not None and to_time is not None and from_time > to_time:
        raise HTTPException(422, "from_time must not be later than to_time")
    actor_id = CTX_USER_ID.get()
    actor = await User.get(id=actor_id)
    await _require_teacher_or_admin(actor)
    data = await get_statistics(actor_id, await is_admin(actor), course_id, class_name, from_time, to_time)
    return Success(data=data)

