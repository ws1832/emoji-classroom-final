"""B 功能测试：学生与教师改密、登录及跨用户和跨课堂权限校验。"""

from datetime import datetime, timedelta

import pytest

from app.api.v1.base import base_router
from app.api.v1.dashboard import dashboard_router
from app.models import Course, User
from app.schemas.login import JWTPayload
from app.utils.jwt_utils import create_access_token
from app.utils.password import get_password_hash, verify_password
from test_classroom_api import _create_course, _create_session


@pytest.mark.parametrize("actor", ["student", "teacher"])
async def test_password_change_and_real_login(client, actor):
    client._transport.app.include_router(base_router, prefix="/api/v1/base")
    user = getattr(client, actor)
    old_password, new_password = "Isolated-old-123", "Isolated-new-456"
    user.password = get_password_hash(old_password)
    await user.save()
    login = await client.post("/api/v1/base/access_token", json={"username": user.username, "password": old_password})
    assert login.status_code == 200
    headers = {"token": login.json()["data"]["access_token"]}
    wrong = await client.post(
        "/api/v1/base/update_password",
        json={"old_password": "incorrect", "new_password": new_password},
        headers=headers,
    )
    assert wrong.status_code == 400
    changed = await client.post(
        "/api/v1/base/update_password",
        json={"old_password": old_password, "new_password": new_password},
        headers=headers,
    )
    assert changed.status_code == 200
    await user.refresh_from_db()
    assert user.password != new_password and verify_password(new_password, user.password)
    rejected = await client.post(
        "/api/v1/base/access_token", json={"username": user.username, "password": old_password}
    )
    accepted = await client.post(
        "/api/v1/base/access_token", json={"username": user.username, "password": new_password}
    )
    assert rejected.status_code == 400 and accepted.status_code == 200
    # 安全修订：密码改变撤销旧JWT，重新登录后的凭证可用。
    assert (await client.get("/api/v1/base/userinfo", headers=headers)).status_code == 401
    fresh = {"token": accepted.json()["data"]["access_token"]}
    assert (await client.get("/api/v1/base/userinfo", headers=fresh)).status_code == 200


async def test_two_teachers_two_students_server_permissions(client):
    client._transport.app.include_router(base_router, prefix="/api/v1/base")
    client._transport.app.include_router(dashboard_router, prefix="/api/v1")
    course = await _create_course(client)
    session = await _create_session(client, course)
    teacher2 = await User.create(
        username="teacher-second",
        email="teacher-second@example.com",
        password=get_password_hash("Isolated-teacher-123"),
        is_active=True,
    )
    await Course.create(name="Second teacher course", teacher_id=teacher2.id)
    login = await client.post(
        "/api/v1/base/access_token", json={"username": teacher2.username, "password": "Isolated-teacher-123"}
    )
    teacher2_headers = {"token": login.json()["data"]["access_token"]}
    await client.post(
        "/api/v1/base/register",
        json={"username": "unscheduled", "email": "unscheduled@example.com", "password": "Isolated-student-123"},
    )
    login = await client.post(
        "/api/v1/base/access_token", json={"username": "unscheduled", "password": "Isolated-student-123"}
    )
    outsider = {"token": login.json()["data"]["access_token"]}
    student, teacher = {"token": client.student_token}, {"token": client.teacher_token}
    assert (
        await client.post(f"/api/v1/sessions/{session}/schedule", json={"user_id": client.student.id}, headers=teacher)
    ).status_code == 200
    for emotion in ["HAPPY", "SAD", "ANGRY", "SURPRISED", "NEUTRAL"]:
        response = await client.post(
            "/api/v1/emoji", json={"session_id": session, "emoji_type": emotion, "source": "MANUAL"}, headers=student
        )
        assert response.status_code == 200
    denied = await client.post(
        "/api/v1/emoji", json={"session_id": session, "emoji_type": "HAPPY", "source": "MANUAL"}, headers=outsider
    )
    assert denied.status_code == 403
    assert (await client.get("/api/v1/emoji/history", headers=outsider)).json()["total"] == 0
    assert (
        await client.get("/api/v1/emoji/history", params={"user_id": client.student.id}, headers=outsider)
    ).status_code == 403
    own = await client.get("/api/v1/emoji", params={"session_id": session}, headers=teacher)
    assert own.json()["total"] == 5
    foreign = await client.get("/api/v1/emoji", params={"session_id": session}, headers=teacher2_headers)
    assert foreign.status_code == 200 and foreign.json()["data"] == [] and foreign.json()["total"] == 0
    for headers in [student, outsider, teacher2_headers]:
        assert (
            await client.get("/api/v1/emoji/statistics", params={"session_id": session}, headers=headers)
        ).status_code == 403
    assert (
        await client.get("/api/v1/dashboard/realtime", params={"session_id": session}, headers=teacher2_headers)
    ).status_code == 403
    summary = (await client.get("/api/v1/emoji/statistics", params={"session_id": session}, headers=teacher)).json()[
        "data"
    ]
    assert len(summary) == 5 and all(row["count"] == 1 and row["percentage"] == 20 for row in summary)
    expired = create_access_token(
        data=JWTPayload(
            user_id=client.student.id,
            username=client.student.username,
            is_superuser=False,
            exp=datetime.now() - timedelta(days=1),
        )
    )
    for token in ["invalid-token", expired]:
        assert (await client.get("/api/v1/emoji/history", headers={"token": token})).status_code == 401
