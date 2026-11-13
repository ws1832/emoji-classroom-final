"""B 功能测试：学生注册登录、排课、情绪提交及教师历史查询闭环。"""

from app.api.v1.base import base_router
from app.api.v1.dashboard import dashboard_router
from test_classroom_api import _create_course, _create_session
from app.utils.password import get_password_hash


async def test_real_student_teacher_flow(client):
    client._transport.app.include_router(base_router, prefix="/api/v1/base")
    client._transport.app.include_router(dashboard_router, prefix="/api/v1")
    password = "Flow-test-123"
    client.student.password = get_password_hash(password)
    client.teacher.password = get_password_hash(password)
    await client.student.save()
    await client.teacher.save()
    from conftest import _make_token

    client.student_token = _make_token(client.student)
    client.teacher_token = _make_token(client.teacher)
    course = await _create_course(client)
    session = await _create_session(client, course)
    teacher = {"token": client.teacher_token}
    r = await client.post(f"/api/v1/sessions/{session}/schedule", json={"user_id": client.student.id}, headers=teacher)
    assert r.status_code == 200
    r = await client.post("/api/v1/base/access_token", json={"username": "student", "password": password})
    assert r.status_code == 200
    student = {"token": r.json()["data"]["access_token"]}
    r = await client.get("/api/v1/base/userinfo", headers=student)
    assert "STUDENT" in r.json()["data"]["role_codes"]
    r = await client.get("/api/v1/sessions/mine", headers=student)
    assert r.status_code == 200 and r.json()["data"][0]["id"] == session
    r = await client.post(
        "/api/v1/emoji", json={"session_id": session, "emoji_type": "HAPPY", "source": "MANUAL"}, headers=student
    )
    assert r.status_code == 200
    record = r.json()["data"]["id"]
    r = await client.get("/api/v1/emoji/history", headers=student)
    assert any(x["id"] == record for x in r.json()["data"])
    r = await client.post("/api/v1/base/access_token", json={"username": "teacher", "password": password})
    assert r.status_code == 200
    teacher = {"token": r.json()["data"]["access_token"]}
    r = await client.get("/api/v1/base/userinfo", headers=teacher)
    assert "TEACHER" in r.json()["data"]["role_codes"]
    r = await client.get("/api/v1/courses", headers=teacher)
    assert any(x["id"] == course for x in r.json()["data"])
    r = await client.get("/api/v1/sessions", params={"course_id": course}, headers=teacher)
    assert any(x["id"] == session for x in r.json()["data"])
    r = await client.get("/api/v1/dashboard/realtime", params={"session_id": session}, headers=teacher)
    assert r.status_code == 200 and r.json()["data"]["session"]["id"] == session
    r = await client.get("/api/v1/emoji", params={"session_id": session}, headers=teacher)
    assert r.status_code == 200
    assert any(x["id"] == record for x in r.json()["data"])
    r = await client.post(
        "/api/v1/base/register", json={"username": "newstudent", "email": "new@example.com", "password": password}
    )
    assert r.status_code == 200
    r = await client.post("/api/v1/base/access_token", json={"username": "newstudent", "password": password})
    outsider = {"token": r.json()["data"]["access_token"]}
    r = await client.get("/api/v1/base/userinfo", headers=outsider)
    assert r.json()["data"]["role_codes"] == ["STUDENT"]
    r = await client.post(
        "/api/v1/courses", json={"name": "forbidden", "teacher_id": r.json()["data"]["id"]}, headers=outsider
    )
    assert r.status_code == 403
    r = await client.get("/api/v1/sessions/mine", headers=outsider)
    assert r.json()["data"] == []
    r = await client.post("/api/v1/emoji", json={"session_id": session, "emoji_type": "HAPPY"}, headers=outsider)
    assert r.status_code == 403
    r = await client.get("/api/v1/dashboard/realtime", params={"session_id": session}, headers=outsider)
    assert r.status_code == 403
    r = await client.post(
        "/api/v1/base/register",
        json={"username": "evil", "email": "evil@example.com", "password": password, "is_superuser": True},
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/base/register", json={"username": "newstudent", "email": "new@example.com", "password": password}
    )
    assert r.status_code == 409
    r = await client.get("/api/v1/base/userinfo", headers={"token": "dev"})
    assert r.status_code == 401
