from app.utils.time import format_beijing

"""手动 Emoji 记录、历史和统计 REST API。"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.controllers.emoji import emoji_controller
from app.controllers.session import session_controller
from app.core.ctx import CTX_USER_ID
from app.core.dependency import DependAuth
from app.models import Course, User
from app.models.enums import EmojiSource, EmojiType
from app.schemas.base import Success, SuccessExtra
from app.schemas.emoji import EmojiCreate
from app.services.export import build_csv_bytes, csv_row_bytes
from app.services.ai_jobs import is_admin

router = APIRouter()


def _validate_time_range(from_time, to_time):
    for value in (from_time, to_time):
        if value is not None and value.utcoffset() is not None:
            raise HTTPException(422, "Use Shanghai local time without a timezone offset")
    if from_time is not None and to_time is not None and from_time > to_time:
        raise HTTPException(422, "from_time must not be later than to_time")


async def _dict(obj):
    return obj if isinstance(obj, dict) else await obj.to_dict()


def _enum_value(value) -> str:
    return str(value.value if hasattr(value, "value") else value)


async def _require_teacher_or_admin(actor: User) -> None:
    if await is_admin(actor):
        return
    has_course = await Course.filter(teacher_id=actor.id).exists()
    if not has_course:
        raise HTTPException(status_code=403, detail="Only teachers and administrators can access emoji data")


@router.get("", response_model=None, dependencies=[DependAuth], summary="查询 Emoji 记录列表")
async def list_emoji(
    session_id: int | None = None,
    user_id: int | None = None,
    user_no: str | None = None,
    emoji_type: EmojiType | None = None,
    source: EmojiSource | None = None,
    course_id: int | None = None,
    class_name: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _validate_time_range(from_time, to_time)
    actor_id = CTX_USER_ID.get()
    actor = await User.get(id=actor_id)
    await _require_teacher_or_admin(actor)
    total, records = await emoji_controller.list_records(
        actor_id,
        await is_admin(actor),
        session_id,
        user_id,
        user_no,
        emoji_type,
        source,
        course_id,
        class_name,
        from_time,
        to_time,
        page,
        page_size,
    )
    data = []
    for record in records:
        item = await record.to_dict()
        item["username"] = record.user.username if record.user else None
        item["user_no"] = record.user.user_no if record.user else None
        item["course_name"] = record.session.course.name if record.session.course else None
        item["class_name"] = record.session.class_name
        item["classroom"] = record.session.classroom
        data.append(item)
    return SuccessExtra(data=data, total=total, page=page, page_size=page_size)


@router.get("/export", response_model=None, dependencies=[DependAuth], summary="导出 Emoji 记录 CSV")
async def export_emoji(
    session_id: int | None = None,
    user_id: int | None = None,
    user_no: str | None = None,
    emoji_type: EmojiType | None = None,
    source: EmojiSource | None = None,
    course_id: int | None = None,
    class_name: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
):
    _validate_time_range(from_time, to_time)
    actor_id = CTX_USER_ID.get()
    actor = await User.get(id=actor_id)
    await _require_teacher_or_admin(actor)
    query = emoji_controller.export_query(
        actor_id,
        await is_admin(actor),
        session_id,
        user_id,
        user_no,
        emoji_type,
        source,
        course_id,
        class_name,
        from_time,
        to_time,
    )
    if await query.count() > 100000:
        raise HTTPException(422, "Export exceeds 100000 rows; narrow the time/course filters")
    newest = await query.order_by("-id").first()
    ceiling = newest.id if newest else 0
    headers = [
        "id",
        "user_id",
        "user_no",
        "username",
        "session_id",
        "course_name",
        "class_name",
        "classroom",
        "emoji_type",
        "source",
        "confidence",
        "device_source",
        "timestamp",
    ]

    async def content():
        yield build_csv_bytes(headers, [])
        async for record in emoji_controller.stream_export_records(query, ceiling=ceiling):
            row = [
                record.id,
                record.user_id or "",
                record.user.user_no if record.user else "",
                record.user.username if record.user else "",
                record.session_id,
                record.session.course.name if record.session.course else "",
                record.session.class_name or "",
                record.session.classroom or "",
                _enum_value(record.emoji_type),
                _enum_value(record.source),
                record.confidence if record.confidence is not None else "",
                record.device_source or "",
                format_beijing(record.timestamp, "%Y-%m-%d %H:%M:%S") if record.timestamp else "",
            ]
            yield csv_row_bytes(row)

    return StreamingResponse(
        content(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="emoji_records.csv"'},
    )


@router.post("", response_model=None, dependencies=[DependAuth], summary="提交 Emoji")
async def create_emoji(payload: EmojiCreate):
    item = await emoji_controller.create_record(payload, actor_id=CTX_USER_ID.get())
    return Success(data=await _dict(item))


@router.get("/history", response_model=None, dependencies=[DependAuth], summary="查询 Emoji 历史")
async def emoji_history(
    user_id: int | None = None,
    session_id: int | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _validate_time_range(from_time, to_time)
    actor_id = CTX_USER_ID.get()
    total, records = await emoji_controller.get_user_history(
        user_id or actor_id, actor_id, session_id, from_time, to_time, page, page_size
    )
    return SuccessExtra(data=[await _dict(item) for item in records], total=total, page=page, page_size=page_size)


@router.get("/statistics", response_model=None, dependencies=[DependAuth], summary="查询 Emoji 统计")
async def emoji_statistics(
    session_id: int | None = Query(None, gt=0),
    user_id: int | None = Query(None, gt=0),
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    source: EmojiSource | None = None,
):
    _validate_time_range(from_time, to_time)
    actor_id = CTX_USER_ID.get()
    if session_id is not None:
        await session_controller.get_for_actor(session_id, actor_id)
    if user_id is not None and user_id != actor_id:
        await emoji_controller.get_user_history(user_id, actor_id, session_id, from_time, to_time, 1, 1)
    data = await emoji_controller.statistics(
        session_id, user_id or (actor_id if session_id is None else None), from_time, to_time, source
    )
    return Success(data=data)
