"""实时课堂情绪看板 REST API。"""

from fastapi import APIRouter, HTTPException, Query

from app.core.ctx import CTX_USER_ID
from app.core.dependency import DependAuth
from app.models import Course, User
from app.schemas.base import Success
from app.services.statistics import get_realtime_dashboard
from app.services.ai_jobs import is_admin

router = APIRouter()


async def _require_teacher_or_admin(actor: User) -> None:
    if await is_admin(actor):
        return
    has_course = await Course.filter(teacher_id=actor.id).exists()
    if not has_course:
        raise HTTPException(status_code=403, detail="Only teachers and administrators can view the dashboard")


@router.get("/realtime", response_model=None, dependencies=[DependAuth], summary="实时课堂情绪看板")
async def realtime_dashboard(session_id: int = Query(..., ge=1, description="课堂会话ID")):
    actor_id = CTX_USER_ID.get()
    actor = await User.get(id=actor_id)
    await _require_teacher_or_admin(actor)
    data = await get_realtime_dashboard(actor_id, await is_admin(actor), session_id)
    if not data.get("found"):
        raise HTTPException(status_code=404, detail="Class session not found")
    if data.get("forbidden"):
        raise HTTPException(status_code=403, detail="Class session does not belong to the teacher")
    return Success(data=data)

