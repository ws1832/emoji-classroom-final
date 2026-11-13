"""设备→课堂任务→租约→幂等匿名入库→既有看板的真实 API 集成。"""

import asyncio
import importlib.util
import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.ai import ai_router, ai_worker_router
from app.api.v1.ai.browser import router as browser_router
from app.api.v1.emoji import emoji_router
from app.api.v1.dashboard import dashboard_router
from app.core.ai_auth import naive, utc_now, wall, wire
from app.core.ai_boundary import AIBoundaryMiddleware
from app.core.init_app import init_apis, init_classroom_menus, init_roles
from app.core.middlewares import HttpAuditLogMiddleware
from app.models import Api, ClassSession, Course, Role, User
from app.models.ai import AICredential, AIJob, AILease, AIReceipt
from app.models.classroom import EmojiRecord
from conftest import _make_token, _register_exceptions


@pytest.fixture
async def ai_client(client):
    await init_classroom_menus()
    await init_apis()
    await init_roles()
    admin = await User.create(username="ai-admin", email="ai-admin@example.com", password="unused", is_superuser=False)
    await admin.roles.add(await Role.get(name="ADMIN"))
    await client.teacher.roles.add(await Role.get(name="TEACHER"))
    await client.student.roles.add(await Role.get(name="STUDENT"))
    course = await Course.create(name="AI-test", teacher_id=client.teacher.id)
    now = wall(utc_now())
    session = await ClassSession.create(
        course_id=course.id, start_time=now - timedelta(minutes=5), end_time=now + timedelta(hours=1)
    )
    app = FastAPI()
    _register_exceptions(app)
    app.add_middleware(HttpAuditLogMiddleware, methods=["POST", "PUT", "DELETE"], exclude_paths=[])
    app.add_middleware(AIBoundaryMiddleware)
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(ai_worker_router, prefix="/api/v1")
    app.include_router(browser_router, prefix="/api/v1")
    app.include_router(emoji_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.admin, c.teacher, c.student, c.session = admin, client.teacher, client.student, session
        c.admin_headers, c.teacher_headers = {"token": _make_token(admin)}, {"token": client.teacher_token}
        c.student_headers = {"token": client.student_token}
        yield c


async def setup_job(c):
    device = await c.post(
        "/api/v1/ai/devices",
        headers=c.admin_headers,
        json={"name": "classroom", "source_alias": "camera-1", "teacher_ids": [c.teacher.id]},
    )
    assert device.status_code == 200, device.text
    c.device = device.json()["data"]
    credential = await c.post(f"/api/v1/ai/devices/{c.device['id']}/credentials", headers=c.admin_headers, json={})
    assert credential.status_code == 200, credential.text
    c.credential = credential.json()["data"]
    c.device_headers = {"Authorization": "Bearer " + c.credential["token"]}
    c.incarnation = str(uuid4())
    beat = await c.post(
        "/api/v1/ai/worker/heartbeat",
        headers=c.device_headers,
        json={"incarnation": c.incarnation, "profiles": ["edge"]},
    )
    assert beat.status_code == 200, beat.text
    payload = {"request_id": str(uuid4()), "session_id": c.session.id, "device_id": c.device["id"], "profile": "edge"}
    job = await c.post("/api/v1/ai/jobs", headers=c.admin_headers, json=payload)
    assert job.status_code == 200, job.text
    c.job = job.json()["data"]
    ready = await c.post(
        f"/api/v1/ai/worker/jobs/{c.job['id']}/ack",
        headers=c.device_headers,
        json={"incarnation": c.incarnation, "generation": c.job["generation"], "observed": "ready"},
    )
    assert ready.status_code == 200, ready.text
    start = await c.post(
        f"/api/v1/ai/jobs/{c.job['id']}/actions",
        headers=c.admin_headers,
        json={"action": "start", "revision": c.job["generation"]},
    )
    assert start.status_code == 200, start.text
    beat = await c.post(
        "/api/v1/ai/worker/heartbeat",
        headers=c.device_headers,
        json={"incarnation": c.incarnation, "profiles": ["edge"]},
    )
    assert beat.status_code == 200, beat.text
    c.job = beat.json()["data"]["jobs"][0]
    return payload


def event(c, **changes):
    return {
        "contract_version": 1,
        "event_id": str(uuid4()),
        "job_id": c.job["id"],
        "generation": c.job["generation"],
        "lease_id": c.job["lease_id"],
        "captured_at": wire(wall(utc_now())),
        "emoji_type": "HAPPY",
        "confidence": 0.95,
        "model_version": c.job["model_version"],
        "config_revision": 1,
        "mapping_version": "five-emotions-v1",
        "quality": {"detection_confidence": 0.95},
        **changes,
    }


async def test_full_scope_idempotency_filter_and_existing_dashboard(ai_client):
    c = ai_client
    await setup_job(c)
    payload = event(c)
    responses = await asyncio.gather(
        *[c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json=payload) for _ in range(4)]
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert [r.json()["data"]["status"] for r in responses].count("accepted") == 1
    assert await EmojiRecord.all().count() == 1
    record = await EmojiRecord.first()
    assert record.user_id is None and record.source == "AI" and record.device_source == "camera-1"
    assert naive(record.timestamp) == naive(wall(utc_now())).replace(microsecond=record.timestamp.microsecond) or naive(
        record.timestamp
    ) <= wall(utc_now())
    conflict = await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json={**payload, "confidence": 0.94})
    assert conflict.status_code == 409
    filtered = event(c, confidence=0.5)
    accepted = await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json=filtered)
    duplicate = await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json=filtered)
    assert accepted.json()["data"]["status"] == "filtered"
    assert duplicate.json()["data"]["decision"] == "filtered"
    assert await AIReceipt.all().count() == 2 and await EmojiRecord.all().count() == 1
    dashboard = await c.get(
        "/api/v1/dashboard/realtime", headers=c.teacher_headers, params={"session_id": c.session.id}
    )
    assert dashboard.json()["data"]["ai_count"] == 1
    assert dashboard.json()["data"]["student_count"] == 0
    admin_dashboard = await c.get(
        "/api/v1/dashboard/realtime", headers=c.admin_headers, params={"session_id": c.session.id}
    )
    assert admin_dashboard.status_code == 200 and admin_dashboard.json()["data"]["ai_count"] == 1
    from app.models import AuditLog

    logs = await AuditLog.all()
    assert all(c.credential["token"] not in str(log.response_body) + str(log.request_args) for log in logs)


async def test_roles_dynamic_permissions_and_device_jwt_separation(ai_client):
    c = ai_client
    await setup_job(c)
    for headers in [c.student_headers, c.teacher_headers, c.admin_headers]:
        assert (await c.post("/api/v1/ai/emoji-results", headers=headers, json=event(c))).status_code == 401
    assert (await c.get("/api/v1/ai/devices", headers=c.student_headers)).status_code == 403
    assert (
        await c.post("/api/v1/ai/devices", headers=c.teacher_headers, json={"name": "x", "source_alias": "x"})
    ).status_code == 403
    other = await User.create(username="ai-other", email="ai-other@example.com", password="unused")
    await other.roles.add(await Role.get(name="TEACHER"))
    assert (await c.get(f"/api/v1/ai/jobs/{c.job['id']}", headers={"token": _make_token(other)})).status_code == 403
    jobs = await c.get("/api/v1/ai/jobs", headers={"token": _make_token(other)})
    assert jobs.json()["data"] == []
    assert (await c.get(f"/api/v1/ai/jobs/{c.job['id']}", headers=c.teacher_headers)).status_code == 200
    stored = await AICredential.get(id=c.credential["credential_id"])
    assert stored.secret_hash != c.credential["token"] and len(stored.secret_hash) == 64
    listing = await c.get("/api/v1/ai/devices", headers=c.admin_headers)
    assert "token" not in listing.text and "secret_hash" not in listing.text
    for headers in [c.teacher_headers, c.student_headers]:
        assert (await c.post("/api/v1/ai/jobs", headers=headers, json={
            "request_id": str(uuid4()), "session_id": c.session.id, "device_id": c.device["id"],
        })).status_code == 403
        assert (await c.post(f"/api/v1/ai/jobs/{c.job['id']}/actions", headers=headers,
                             json={"action": "stop", "revision": c.job["generation"]})).status_code == 403


async def test_pause_stop_late_capture_fencing_revoke_and_active_slot(ai_client):
    c = ai_client
    payload = await setup_job(c)
    old = event(c)
    pause = await c.post(
        f"/api/v1/ai/jobs/{c.job['id']}/actions",
        headers=c.admin_headers,
        json={"action": "pause", "revision": c.job["generation"]},
    )
    assert pause.status_code == 200
    late = await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json=old)
    assert late.status_code == 200  # 停止前授权的 outbox 可补交。
    stale = await c.post(
        f"/api/v1/ai/worker/jobs/{c.job['id']}/ack",
        headers=c.device_headers,
        json={
            "incarnation": c.incarnation,
            "generation": c.job["generation"],
            "observed": "running",
            "lease_id": c.job["lease_id"],
        },
    )
    assert stale.status_code == 409
    after_pause = event(c)
    assert (await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json=after_pause)).status_code == 422
    duplicate_create = await c.post(
        "/api/v1/ai/jobs", headers=c.admin_headers, json={**payload, "request_id": str(uuid4())}
    )
    assert duplicate_create.status_code == 409
    revoked = await c.delete(f"/api/v1/ai/devices/{c.device['id']}/credentials", headers=c.admin_headers)
    assert revoked.status_code == 200
    assert (await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json=old)).status_code == 401
    assert (await AIJob.get(id=c.job["id"])).active_slot is None
    assert await AILease.filter(revoked=False).count() == 0


async def test_worker_incarnation_conflict_and_safe_invalid_body(ai_client):
    c = ai_client
    await setup_job(c)
    second = await c.post(
        "/api/v1/ai/worker/heartbeat",
        headers=c.device_headers,
        json={"incarnation": str(uuid4()), "profiles": ["edge"]},
    )
    assert second.status_code == 409
    secret = "sensitive-raw-image"
    response = await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json={**event(c), "image": secret})
    assert response.status_code == 422 and secret not in response.text
    huge = await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json={"image": "x" * (256 * 1024)})
    assert huge.status_code == 413
    wrong = await c.post(
        "/api/v1/ai/emoji-results",
        headers=c.device_headers,
        content=b"raw",
    )
    assert wrong.status_code == 415

    async def chunks():
        yield b'{"image":"'
        yield b"x" * (256 * 1024)

    assert (
        await c.post(
            "/api/v1/ai/emoji-results",
            headers={**c.device_headers, "Content-Type": "application/json"},
            content=chunks(),
        )
    ).status_code == 413
    from app.models import AuditLog

    logs = await AuditLog.all()
    assert logs and all(log.request_args == {"metadata_only": True} for log in logs)
    assert all(secret not in str(log.request_args) + str(log.response_body) for log in logs)


async def test_incremental_api_initialization_retains_custom_grants(ai_client):
    role = await Role.get(name="TEACHER")
    custom = await Api.create(path="/custom", method="GET", summary="custom", tags="custom")
    await role.apis.add(custom)
    old_write = await Api.get(path="/api/v1/ai/jobs", method="POST")
    await role.apis.add(old_write)
    await init_apis()
    await init_roles()
    count = await Api.filter(tags="AI控制").count()
    await init_apis()
    assert await Api.filter(tags="AI控制").count() == count
    assert await role.apis.filter(id=custom.id).exists()
    assert not await role.apis.filter(path__contains="credentials").exists()
    assert not await role.apis.filter(id=old_write.id).exists()
    assert not await Api.filter(tags="AI设备服务").exists()


async def test_ai_additive_sqlite_migration_preserves_existing_records(tmp_path):
    root = Path(__file__).resolve().parents[1]
    with sqlite3.connect(tmp_path / "upgrade.sqlite3") as db:
        for path in sorted((root / "migrations/models").glob("[0123]_*.py")):
            spec = importlib.util.spec_from_file_location("migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            db.executescript(await module.upgrade(None))
        assert db.execute("SELECT count(*) FROM ai_device").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM emoji_record").fetchone()[0] == 0
        db.executescript((root / "database/ai_sqlite_upgrade.sql").read_text(encoding="utf-8"))
