"""高频匿名观测仍保持 A/B/C 合同；有界导出游标和 SQL 时间分桶。"""

from datetime import datetime, timedelta

from app.controllers.emoji import emoji_controller
from app.models import ClassSession, Course, EmojiRecord
from app.services.statistics import get_realtime_dashboard, get_statistics


async def test_aggregation_and_keyset_with_same_timestamps(client):
    course = await Course.create(name="capacity", teacher_id=client.teacher.id)
    start = datetime(2026, 11, 11, 23, 59)
    session = await ClassSession.create(course_id=course.id, start_time=start, end_time=start + timedelta(hours=1))
    await EmojiRecord.bulk_create(
        [
            EmojiRecord(
                session_id=session.id,
                user_id=None,
                emoji_type="NEUTRAL",
                source="AI",
                confidence=0.9,
                timestamp=start + timedelta(seconds=i % 120),
            )
            for i in range(1200)
        ]
    )
    aggregate = await get_statistics(client.teacher.id, False)
    assert aggregate["overview"]["total_records"] == 1200
    assert aggregate["overview"]["total_students"] == 0
    assert aggregate["by_day"] == [{"day": "2026-11-11", "count": 600}, {"day": "2026-11-12", "count": 600}]
    dashboard = await get_realtime_dashboard(client.teacher.id, False, session.id)
    assert dashboard["timeline"] == [
        {"time": "2026-11-11 23:59", "count": 600},
        {"time": "2026-11-12 00:00", "count": 600},
    ]
    query = emoji_controller.export_query(client.teacher.id, False, session_id=session.id)
    ceiling = (await query.order_by("-id").first()).id
    await EmojiRecord.create(session_id=session.id, emoji_type="HAPPY", source="AI", confidence=0.9, timestamp=start)
    rows = [r.id async for r in emoji_controller.stream_export_records(query, ceiling=ceiling, batch_size=97)]
    assert len(rows) == len(set(rows)) == 1200
    expected = await query.filter(id__lte=ceiling).order_by("-timestamp", "-id").values_list("id", flat=True)
    assert rows == expected
    assert (await get_statistics(client.student.id, False))["overview"]["total_records"] == 0
