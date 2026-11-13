"""D 与 A/B/C 的真实 API 契约回归，不把伪设备数据写入当作正式 AI 验收。"""

import csv
import io
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.controllers.emoji import emoji_controller
from app.models import EmojiRecord, ScheduleUser, User
from app.models.enums import EmojiSource, EmojiType
from app.schemas.ai import AIIngestEvent
from app.schemas.emoji import EmojiCreate
from app.services.ai_ingest import business_timestamp
from conftest import _make_token
from test_classroom_api import _create_course, _create_session
from test_d_ai_contract import event_payload


@pytest.mark.parametrize("actor", ["student", "teacher", "admin"])
async def test_all_user_jwts_cannot_forge_ai_source(client, actor):
    session_id = await _create_session(client, await _create_course(client))
    await ScheduleUser.create(session_id=session_id, user_id=client.student.id)
    if actor == "admin":
        user = await User.create(username="admin-d", email="admin-d@example.com", password="unused", is_superuser=True)
    else:
        user = getattr(client, actor)
    token = _make_token(user)
    response = await client.post(
        "/api/v1/emoji",
        headers={"token": token},
        json={"session_id": session_id, "emoji_type": "HAPPY", "source": "AI", "confidence": 0.9},
    )
    assert response.status_code == 403
    assert response.json() == {"code": 403, "msg": "AI records require an independent device credential", "data": None}
    assert await EmojiRecord.all().count() == 0
    # 共享控制器也拒绝，避免之后添加另一个用户路由时重新暴露旁路。
    with pytest.raises(HTTPException) as denied:
        await emoji_controller.create_record(
            EmojiCreate(session_id=session_id, emoji_type="HAPPY", source="AI", confidence=0.9), actor_id=user.id
        )
    assert denied.value.status_code == 403
    if actor == "student":
        manual = await client.post(
            "/api/v1/emoji", headers={"token": token}, json={"session_id": session_id, "emoji_type": "HAPPY"}
        )
        assert manual.status_code == 200
        assert manual.json()["data"]["source"] == "MANUAL"
        assert manual.json()["data"]["user_id"] == user.id


async def test_same_anonymous_records_visible_in_existing_history_stats_dashboard_and_csv(client):
    session_id = await _create_session(client, await _create_course(client))
    await ScheduleUser.create(session_id=session_id, user_id=client.student.id)
    captured = business_timestamp(AIIngestEvent.model_validate(event_payload()))
    for emoji_type in EmojiType:
        item = await EmojiRecord.create(
            session_id=session_id,
            user_id=None,
            emoji_type=emoji_type,
            source=EmojiSource.AI,
            confidence=0.91,
            device_source="=camera-1",
            timestamp=captured,
        )
        # 锁定 ORM 的 auto_now_add 不覆盖显式采样时间。
        await item.refresh_from_db()
        assert item.timestamp.replace(tzinfo=None) == captured
    await EmojiRecord.create(
        session_id=session_id,
        user_id=client.student.id,
        emoji_type=EmojiType.HAPPY,
        source=EmojiSource.MANUAL,
        timestamp=datetime(2026, 11, 12, 0, 0, 1),
    )
    headers = {"token": client.teacher_token}
    listing = (
        await client.get("/api/v1/emoji", params={"session_id": session_id, "source": "AI"}, headers=headers)
    ).json()
    assert listing["total"] == 5 and listing["page"] == 1 and listing["page_size"] == 20
    assert all(row["user_id"] is None and row["username"] is None for row in listing["data"])
    assert all(row["timestamp"] == "2026-11-12 00:00:00" for row in listing["data"])
    # 旧自动序列化不可泄漏新 AI 的内部字段。
    assert set(listing["data"][0]) == {
        "id",
        "user_id",
        "session_id",
        "emoji_type",
        "timestamp",
        "source",
        "confidence",
        "device_source",
        "username",
        "user_no",
        "course_name",
        "class_name",
        "classroom",
    }
    stats = (
        await client.get("/api/v1/emoji/statistics", params={"session_id": session_id, "source": "AI"}, headers=headers)
    ).json()["data"]
    assert {row["emoji_type"] for row in stats} == {value.value for value in EmojiType}
    assert all(row["count"] == 1 and row["percentage"] == 20 for row in stats)
    history = (
        await client.get(
            "/api/v1/emoji/history", params={"session_id": session_id}, headers={"token": client.student_token}
        )
    ).json()
    assert history["total"] == 1 and history["data"][0]["source"] == "MANUAL"
    dashboard = (
        await client.get("/api/v1/dashboard/realtime", params={"session_id": session_id}, headers=headers)
    ).json()["data"]
    assert (dashboard["total_count"], dashboard["ai_count"], dashboard["manual_count"], dashboard["student_count"]) == (
        6,
        5,
        1,
        1,
    )
    assert dashboard["timeline"] == [{"time": "2026-11-12 00:00", "count": 6}]
    aggregate = (await client.get("/api/v1/statistics", headers=headers)).json()["data"]["overview"]
    assert aggregate == {"total_records": 6, "total_students": 1, "manual_records": 1, "ai_records": 5}
    exported = await client.get(
        "/api/v1/emoji/export", params={"session_id": session_id, "source": "AI"}, headers=headers
    )
    rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert rows[0] == [
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
    assert len(rows) == 6
    assert all(
        row[1:4] == ["", "", ""] and row[-2] == "'=camera-1" and row[-1] == "2026-11-12 00:00:00" for row in rows[1:]
    )
    assert {row[8] for row in rows[1:]} == {row["emoji_type"] for row in stats}
