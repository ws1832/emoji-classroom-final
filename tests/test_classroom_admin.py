"""C 模块测试：管理端统计、实时看板、CSV 导出、Emoji 列表与排课列表。"""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.api.v1.courses import courses_router
from app.api.v1.dashboard import dashboard_router
from app.api.v1.emoji import emoji_router
from app.api.v1.sessions import sessions_router
from app.api.v1.statistics import statistics_router
from app.core.exceptions import (
    DoesNotExist,
    DoesNotExistHandle,
    HTTPException,
    HttpExcHandle,
    IntegrityError,
    IntegrityHandle,
    RequestValidationError,
    RequestValidationHandle,
    ResponseValidationError,
    ResponseValidationHandle,
)
from app.models import EmojiRecord, User
from app.models.enums import EmojiSource, EmojiType
from app.schemas.login import JWTPayload
from app.services.export import build_csv, build_csv_bytes
from app.utils.jwt_utils import create_access_token, credential_tag


def _register_exceptions(app: FastAPI) -> None:
    app.add_exception_handler(DoesNotExist, DoesNotExistHandle)
    app.add_exception_handler(HTTPException, HttpExcHandle)
    app.add_exception_handler(IntegrityError, IntegrityHandle)
    app.add_exception_handler(RequestValidationError, RequestValidationHandle)
    app.add_exception_handler(ResponseValidationError, ResponseValidationHandle)


def _make_token(user: User) -> str:
    payload = JWTPayload(
        user_id=user.id,
        username=user.username,
        is_superuser=user.is_superuser,
        exp=datetime.now() + timedelta(hours=1),
        credential_tag=credential_tag(user.password),
    )
    return create_access_token(data=payload)


@pytest.fixture
async def client(tmp_path):
    config = {
        "connections": {
            "default": {
                "engine": "tortoise.backends.sqlite",
                "credentials": {"file_path": str(tmp_path / "admin_test.sqlite3")},
            }
        },
        "apps": {
            "models": {
                "models": ["app.models"],
                "default_connection": "default",
            }
        },
        "use_tz": False,
        "timezone": "Asia/Shanghai",
    }

    await Tortoise.init(config=config)
    await Tortoise.generate_schemas()

    admin = await User.create(
        username="admin", email="admin@example.com", password="hashed", is_active=True, is_superuser=True
    )
    teacher = await User.create(
        username="teacher", email="teacher@example.com", password="hashed", is_active=True, is_superuser=False
    )
    student = await User.create(
        username="student", email="student@example.com", password="hashed", is_active=True, is_superuser=False
    )

    app = FastAPI(title="emoji-classroom-admin-test")
    _register_exceptions(app)
    app.include_router(courses_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(emoji_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(statistics_router, prefix="/api/v1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        test_client.admin = admin
        test_client.teacher = teacher
        test_client.student = student
        test_client.admin_token = _make_token(admin)
        test_client.teacher_token = _make_token(teacher)
        test_client.student_token = _make_token(student)
        yield test_client

    await Tortoise.close_connections()


async def _seed_classroom(client):
    """创建课程、课堂、排课并写入一条手动和一条 AI Emoji，返回 session_id。"""

    headers = {"token": client.teacher_token}
    resp = await client.post(
        "/api/v1/courses", json={"name": "数据结构", "teacher_id": client.teacher.id}, headers=headers
    )
    course_id = resp.json()["data"]["id"]

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
    session_id = resp.json()["data"]["id"]

    await client.post(f"/api/v1/sessions/{session_id}/schedule", json={"user_id": client.student.id}, headers=headers)
    await client.post(
        "/api/v1/emoji",
        json={"user_id": client.student.id, "session_id": session_id, "emoji_type": "HAPPY", "source": "MANUAL"},
        headers=headers,
    )
    # 统计 fixture 直接准备业务记录，不借教师 JWT 冒充 AI 服务。
    await EmojiRecord.create(session_id=session_id, emoji_type=EmojiType.SAD, source=EmojiSource.AI, confidence=0.9)
    return session_id


# ---------- CSV 导出单元测试 ----------


def test_export_csv_escaping():
    headers = ["name", "value"]
    rows = [["普通值", "hello, world"], ["公式", "=SUM(A1)"], ["负数", "-1"], ["符号", "@cmd"], ["换行", "a\nb"]]
    content = build_csv(headers, rows)
    assert '"hello, world"' in content
    assert "'=SUM(A1)" in content
    assert "'-1" in content
    assert "'@cmd" in content


def test_export_csv_bytes_has_bom():
    content = build_csv_bytes(["a"], [["b"]])
    assert content.startswith(b"\xef\xbb\xbf")


# ---------- C 模块接口测试 ----------


async def test_schedule_list_endpoint(client):
    session_id = await _seed_classroom(client)
    headers = {"token": client.teacher_token}
    resp = await client.get(f"/api/v1/sessions/{session_id}/schedule", headers=headers)
    assert resp.status_code == 200
    users = resp.json()["data"]
    assert any(item["user_id"] == client.student.id for item in users)


async def test_emoji_admin_list(client):
    await _seed_classroom(client)
    headers = {"token": client.admin_token}
    resp = await client.get("/api/v1/emoji", headers=headers, params={"page": 1, "page_size": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert any(item["username"] == "student" for item in body["data"])


async def test_statistics_endpoint(client):
    await _seed_classroom(client)
    headers = {"token": client.admin_token}
    resp = await client.get("/api/v1/statistics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["overview"]["total_records"] == 2
    assert data["overview"]["manual_records"] == 1
    assert data["overview"]["ai_records"] == 1
    types = {item["emoji_type"]: item["count"] for item in data["by_type"]}
    assert types["HAPPY"] == 1
    assert types["SAD"] == 1


async def test_dashboard_endpoint(client):
    session_id = await _seed_classroom(client)
    headers = {"token": client.teacher_token}
    resp = await client.get("/api/v1/dashboard/realtime", headers=headers, params={"session_id": session_id})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_count"] == 2
    assert data["manual_count"] == 1
    assert data["ai_count"] == 1
    assert len(data["summary"]) == 2


async def test_emoji_export_endpoint(client):
    await _seed_classroom(client)
    headers = {"token": client.admin_token}
    resp = await client.get("/api/v1/emoji/export", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "emoji_type" in resp.text


async def test_statistics_forbidden_for_student(client):
    headers = {"token": client.student_token}
    resp = await client.get("/api/v1/statistics", headers=headers)
    assert resp.status_code == 403


async def test_dashboard_forbidden_for_student(client):
    session_id = await _seed_classroom(client)
    headers = {"token": client.student_token}
    resp = await client.get("/api/v1/dashboard/realtime", headers=headers, params={"session_id": session_id})
    assert resp.status_code == 403
