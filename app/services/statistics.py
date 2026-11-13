"""同一权限范围内数据库聚合；不加载全部 AI 记录到 Python。"""

from datetime import datetime

from tortoise.functions import Count
from tortoise.expressions import RawSQL

from app.models.classroom import ClassSession, EmojiRecord
from app.services.time_bucket import TimeBucket
from app.utils.time import format_beijing


def _ratio(count, total):
    return round(count * 100 / total, 2) if total else 0.0


async def _groups(query, *fields):
    return (
        await query.annotate(count=Count("id")).group_by(*fields).order_by("-count", *fields).values(*fields, "count")
    )


async def _buckets(query, precision):
    dialect = query.model._meta.db.capabilities.dialect
    return await (
        query.annotate(bucket=TimeBucket("timestamp", precision, dialect), count=Count("id"))
        .group_by("bucket")
        .order_by("bucket")
        .values("bucket", "count")
    )


async def _totals(query):
    # Tortoise 对含 JOIN 的 aggregate 自动按主键分组，显式常量组避免返回每条记录一行。
    rows = (
        await query.annotate(
            all_records=RawSQL("'all'"),
            total=Count("id"),
            students=Count("user_id", distinct=True),
        )
        .group_by("all_records")
        .values("all_records", "total", "students")
    )
    return rows[0] if rows else {"total": 0, "students": 0}


async def get_statistics(
    actor_id: int,
    is_superuser: bool,
    course_id: int | None = None,
    class_name: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
) -> dict:
    query = EmojiRecord.all()
    if not is_superuser:
        query = query.filter(session__course__teacher_id=actor_id)
    if course_id is not None:
        query = query.filter(session__course_id=course_id)
    if class_name:
        query = query.filter(session__class_name=class_name)
    if from_time is not None:
        query = query.filter(timestamp__gte=from_time)
    if to_time is not None:
        query = query.filter(timestamp__lte=to_time)
    totals = await _totals(query)
    total = totals["total"]
    types = await _groups(query, "emoji_type")
    sources = await _groups(query, "source")
    courses = await _groups(query, "session__course_id", "session__course__name")
    class_rows = await _groups(query, "session__class_name")
    classes = {}
    for row in class_rows:
        name = row["session__class_name"] or "未分班"
        classes[name] = classes.get(name, 0) + row["count"]
    source_count = {row["source"]: row["count"] for row in sources}
    return {
        "overview": {
            "total_records": total,
            "total_students": totals["students"],
            "manual_records": source_count.get("MANUAL", 0),
            "ai_records": source_count.get("AI", 0),
        },
        "by_type": [
            {"emoji_type": r["emoji_type"], "count": r["count"], "percentage": _ratio(r["count"], total)} for r in types
        ],
        "by_course": [
            {
                "course_id": r["session__course_id"],
                "course_name": r["session__course__name"],
                "count": r["count"],
                "percentage": _ratio(r["count"], total),
            }
            for r in courses
        ],
        "by_class": [
            {"class_name": name, "count": count, "percentage": _ratio(count, total)}
            for name, count in sorted(classes.items(), key=lambda item: (-item[1], item[0]))
        ],
        "by_source": [
            {"source": r["source"], "count": r["count"], "percentage": _ratio(r["count"], total)} for r in sources
        ],
        "by_day": [{"day": r["bucket"], "count": r["count"]} for r in await _buckets(query, "day")],
        "by_hour": [{"hour": r["bucket"], "count": r["count"]} for r in await _buckets(query, "hour")],
    }


async def get_realtime_dashboard(actor_id: int, is_superuser: bool, session_id: int) -> dict:
    session = await ClassSession.get_or_none(id=session_id).prefetch_related("course")
    if session is None:
        return {"found": False}
    if not is_superuser and session.course.teacher_id != actor_id:
        return {"found": True, "forbidden": True}
    query = EmojiRecord.filter(session_id=session_id)
    totals = await _totals(query)
    total = totals["total"]
    sources = {row["source"]: row["count"] for row in await _groups(query, "source")}
    return {
        "found": True,
        "forbidden": False,
        "session": {
            "id": session.id,
            "course_id": session.course_id,
            "course_name": session.course.name,
            "class_name": session.class_name,
            "classroom": session.classroom,
            "start_time": format_beijing(session.start_time, "%Y-%m-%d %H:%M:%S"),
            "end_time": format_beijing(session.end_time, "%Y-%m-%d %H:%M:%S"),
        },
        "summary": [
            {"emoji_type": r["emoji_type"], "count": r["count"], "percentage": _ratio(r["count"], total)}
            for r in await _groups(query, "emoji_type")
        ],
        "total_count": total,
        "student_count": totals["students"],
        "manual_count": sources.get("MANUAL", 0),
        "ai_count": sources.get("AI", 0),
        "timeline": [{"time": r["bucket"], "count": r["count"]} for r in await _buckets(query, "minute")],
    }
