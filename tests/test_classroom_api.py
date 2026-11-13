"""A 模块接口测试：课程、课堂会话、排课和 Emoji 记录的 REST 接口。"""

from app.models import Role, User
from conftest import _make_token


async def test_regular_admin_manages_all_courses_and_sessions_without_ownership(client):
    admin = await User.create(username="regular-admin", email="regular-admin@example.com", password="unused")
    role, _ = await Role.get_or_create(name="ADMIN")
    await admin.roles.add(role)
    headers = {"token": _make_token(admin)}
    course_id = await _create_course(client, name="管理员全局范围")
    session_id = await _create_session(client, course_id)
    for path, identifier in [("/courses", course_id), ("/sessions", session_id)]:
        result = await client.get("/api/v1" + path, headers=headers)
        assert result.status_code == 200 and identifier in [item["id"] for item in result.json()["data"]]
    created = await client.post("/api/v1/courses", headers=headers,
                                json={"name": "管理员建课", "teacher_id": client.teacher.id})
    assert created.status_code == 200
    assert (await client.post(f"/api/v1/sessions/{session_id}/schedule", headers=headers,
                              json={"user_id": client.student.id})).status_code == 200
    assert (await client.delete(f"/api/v1/sessions/{session_id}", headers=headers)).status_code == 200
    assert (await client.delete(f"/api/v1/courses/{course_id}", headers=headers)).status_code == 200


async def _create_course(client, name="数据结构"):
    headers = {"token": client.teacher_token}
    resp = await client.post(
        "/api/v1/courses",
        json={"name": name, "teacher_id": client.teacher.id, "description": "接口测试课程"},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


async def _create_session(client, course_id):
    headers = {"token": client.teacher_token}
    resp = await client.post(
        "/api/v1/sessions",
        json={
            "course_id": course_id,
            "start_time": "2026-11-03T10:00:00",
            "end_time": "2026-11-03T11:00:00",
            "classroom": "A101",
            "class_name": "计科2301",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


async def test_course_lifecycle(client):
    headers = {"token": client.teacher_token}

    resp = await client.post(
        "/api/v1/courses",
        json={"name": "数据结构", "teacher_id": client.teacher.id, "description": "计算机基础课"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    course_id = body["data"]["id"]
    assert body["data"]["name"] == "数据结构"
    assert body["data"]["teacher_id"] == client.teacher.id

    resp = await client.get("/api/v1/courses", headers=headers)
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["total"] >= 1
    assert any(item["id"] == course_id for item in listing["data"])


async def test_session_time_range_validation(client):
    course_id = await _create_course(client, name="离散数学")

    headers = {"token": client.teacher_token}
    resp = await client.post(
        "/api/v1/sessions",
        json={
            "course_id": course_id,
            "start_time": "2026-11-03T10:00:00",
            "end_time": "2026-11-03T09:00:00",
        },
        headers=headers,
    )
    assert resp.status_code == 422

    session_id = await _create_session(client, course_id)
    assert session_id > 0


async def test_schedule_and_manual_emoji_flow(client):
    course_id = await _create_course(client, name="操作系统")
    session_id = await _create_session(client, course_id)
    headers = {"token": client.teacher_token}

    resp = await client.post(
        f"/api/v1/sessions/{session_id}/schedule",
        json={"user_id": client.student.id},
        headers=headers,
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/api/v1/emoji",
        json={
            "user_id": client.student.id,
            "session_id": session_id,
            "emoji_type": "HAPPY",
            "source": "MANUAL",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    record = resp.json()["data"]
    assert record["emoji_type"] == "HAPPY"
    assert record["source"] == "MANUAL"

    resp = await client.get("/api/v1/emoji/statistics", params={"session_id": session_id}, headers=headers)
    assert resp.status_code == 200
    stats = resp.json()["data"]
    assert any(item["emoji_type"] == "HAPPY" and item["count"] == 1 for item in stats)


async def test_emoji_source_validation(client):
    course_id = await _create_course(client, name="计算机网络")
    session_id = await _create_session(client, course_id)
    headers = {"token": client.teacher_token}

    resp = await client.post(
        "/api/v1/emoji",
        json={
            "user_id": client.student.id,
            "session_id": session_id,
            "emoji_type": "SAD",
            "source": "MANUAL",
            "confidence": 0.5,
        },
        headers=headers,
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/emoji",
        json={"session_id": session_id, "emoji_type": "HAPPY", "source": "AI"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_student_cannot_manage_others_course(client):
    teacher_headers = {"token": client.teacher_token}
    resp = await client.post(
        "/api/v1/courses",
        json={"name": "编译原理", "teacher_id": client.teacher.id},
        headers=teacher_headers,
    )
    course_id = resp.json()["data"]["id"]

    student_headers = {"token": client.student_token}
    resp = await client.delete(f"/api/v1/courses/{course_id}", headers=student_headers)
    assert resp.status_code == 403


async def test_student_must_be_scheduled_to_send_emoji(client):
    course_id = await _create_course(client, name="人工智能导论")
    session_id = await _create_session(client, course_id)

    student_headers = {"token": client.student_token}
    resp = await client.post(
        "/api/v1/emoji",
        json={"session_id": session_id, "emoji_type": "HAPPY", "source": "MANUAL"},
        headers=student_headers,
    )
    assert resp.status_code == 403


async def test_course_update_uses_path_id_and_teacher_cannot_delete(client):
    headers = {"token": client.teacher_token}
    course_id = await _create_course(client, name="软件工程")

    resp = await client.put(
        f"/api/v1/courses/{course_id}",
        json={"name": "软件工程（改）", "description": "更新后的课程"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "软件工程（改）"

    resp = await client.delete(f"/api/v1/courses/{course_id}", headers=headers)
    assert resp.status_code == 403

    resp = await client.get("/api/v1/courses", headers=headers)
    assert any(item["id"] == course_id for item in resp.json()["data"])


async def test_session_update_uses_path_id(client):
    course_id = await _create_course(client, name="数据库原理")
    session_id = await _create_session(client, course_id)
    headers = {"token": client.teacher_token}

    resp = await client.put(
        f"/api/v1/sessions/{session_id}",
        json={"classroom": "B202"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["classroom"] == "B202"
