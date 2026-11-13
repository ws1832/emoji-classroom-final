"""学生授权、配额、服务票据、匿名写库与既有看板的接口闭环。"""

import csv as csv_module
import io
from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.ai_auth import utc_now, wall
from app.models import BrowserCapture, BrowserFrame, EmojiRecord, ScheduleUser, AuditLog, AIJob, Api, Role, User
from app.settings import settings
from test_d_ai_api import ai_client as fixture_ai_client, event
from conftest import _make_token

ai_client = fixture_ai_client


async def prepare(c, monkeypatch):
    r = await c.post(
        "/api/v1/ai/devices",
        headers=c.admin_headers,
        json={"name": "browser-service", "source_alias": "student-browser", "teacher_ids": []},
    )
    device = r.json()["data"]["id"]
    monkeypatch.setattr(settings, "AI_BROWSER_DEVICE_ID", device)
    monkeypatch.setattr(settings, "AI_BROWSER_UPLOAD_URL", "/ai-stream/frames")
    r = await c.post(f"/api/v1/ai/devices/{device}/credentials", headers=c.admin_headers, json={})
    c.device_headers = {"Authorization": "Bearer " + r.json()["data"]["token"]}
    c.incarnation = str(uuid4())
    await beat(c)
    await ScheduleUser.create(user_id=c.student.id, session_id=c.session.id)
    r = await c.put(
        f"/api/v1/ai/browser/manage/{c.session.id}",
        headers=c.admin_headers,
        json={"enabled": True, "revision": 0, "sample_interval": 10, "threshold": 0.7},
    )
    assert r.status_code == 200, r.text
    await beat(c)
    r = await c.post(
        f"/api/v1/ai/browser/classrooms/{c.session.id}/captures", headers=c.student_headers, json={"consent": True}
    )
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store" and "headers" not in r.json()
    c.capture = r.json()["data"]


async def beat(c):
    r = await c.post(
        "/api/v1/ai/worker/heartbeat",
        headers=c.device_headers,
        json={"incarnation": c.incarnation, "profiles": ["edge"]},
    )
    assert r.status_code == 200, r.text
    if r.json()["data"]["jobs"]:
        c.job = r.json()["data"]["jobs"][0]


def claim_body(c, **changes):
    return {
        "capture_token": c.capture["capture_token"],
        "event_id": str(uuid4()),
        "payload_hash": "a" * 64,
        "incarnation": c.incarnation,
        **changes,
    }


async def test_browser_anonymous_end_to_end_and_single_effect(ai_client, monkeypatch):
    c = ai_client
    await prepare(c, monkeypatch)
    body = claim_body(c)
    r = await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=body)
    assert r.status_code == 200, r.text
    ticket = r.json()["data"]
    r = await c.post(
        "/api/v1/ai/browser/worker/outcomes",
        headers=c.device_headers,
        json={"event_id": body["event_id"], "reason": "ready", "faces": 1, "inference_ms": 10},
    )
    assert r.status_code == 200, r.text
    payload = event(c, event_id=body["event_id"], captured_at=ticket["captured_at"])
    for _ in range(2):
        r = await c.post("/api/v1/ai/emoji-results", headers=c.device_headers, json=payload)
        assert r.status_code == 200, r.text
    assert await EmojiRecord.all().count() == 1
    record = await EmojiRecord.first()
    assert record.user_id is None and record.device_source == "student-browser"
    job = await AIJob.get(id=c.job["id"])
    assert job.metrics["sampled"] == job.metrics["published"] == 1
    r = await c.get("/api/v1/dashboard/realtime", headers=c.teacher_headers, params={"session_id": c.session.id})
    assert r.json()["data"]["ai_count"] == 1
    r = await c.get(f"/api/v1/ai/browser/manage/{c.session.id}", headers=c.teacher_headers)
    assert "capture_token" not in r.text and "owner" not in r.text
    csv = await c.get("/api/v1/emoji/export", headers=c.admin_headers, params={"session_id": c.session.id})
    assert csv.status_code == 200 and len(csv.text.splitlines()) == 2
    assert "AI" in csv.text and "student-browser" in csv.text
    exported = list(csv_module.DictReader(io.StringIO(csv.text.lstrip("\ufeff"))))
    assert exported[0]["user_id"] == ""
    logs = await AuditLog.all()
    assert all(c.capture["capture_token"] not in str(x.request_args) + str(x.response_body) for x in logs)


async def test_single_session_reopen_does_not_reset_quota(ai_client, monkeypatch):
    c = ai_client
    await prepare(c, monkeypatch)
    base = f"/api/v1/ai/browser/classrooms/{c.session.id}/captures"
    assert (await c.post(base, headers=c.student_headers, json={"consent": True})).status_code == 409
    body = claim_body(c)
    assert (await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=body)).status_code == 200
    duplicate = await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=body)
    assert duplicate.json()["data"] == {"duplicate": True, "reason": "waiting", "state": "claimed"}
    assert (
        await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=claim_body(c))
    ).status_code == 429
    old_phase = c.capture["phase_ms"]
    r = await c.post(f"/api/v1/ai/browser/captures/{c.capture['capture_id']}/stop", headers=c.student_headers, json={})
    assert r.status_code == 200, r.text
    stopped = await BrowserCapture.first()
    assert stopped.owner_id is None and stopped.token_hash == "" and stopped.active_key is None
    r = await c.post(base, headers=c.student_headers, json={"consent": True})
    c.capture = r.json()["data"]
    assert c.capture["phase_ms"] == old_phase
    assert (
        await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=claim_body(c))
    ).status_code == 429
    assert await BrowserFrame.all().count() == 1


@pytest.mark.parametrize("reason,faces", [("no_face", 0), ("multi_face", 2), ("filtered", 1)])
async def test_rejection_never_creates_neutral_record(ai_client, monkeypatch, reason, faces):
    c = ai_client
    await prepare(c, monkeypatch)
    body = claim_body(c)
    r = await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=body)
    ticket = r.json()["data"]
    for _ in range(2):
        r = await c.post(
            "/api/v1/ai/browser/worker/outcomes",
            headers=c.device_headers,
            json={"event_id": body["event_id"], "reason": reason, "faces": faces},
        )
        assert r.status_code == 200
    r = await c.post(
        "/api/v1/ai/emoji-results",
        headers=c.device_headers,
        json=event(c, event_id=body["event_id"], captured_at=ticket["captured_at"]),
    )
    assert r.status_code == 410
    assert await EmojiRecord.all().count() == 0
    assert (await AIJob.get(id=c.job["id"])).metrics["sampled"] == 1


async def test_permissions_expiry_and_stop(ai_client, monkeypatch):
    c = ai_client
    await prepare(c, monkeypatch)
    manage = f"/api/v1/ai/browser/manage/{c.session.id}"
    assert (await c.get(manage, headers=c.student_headers)).status_code == 403
    assert (
        await c.post("/api/v1/ai/browser/worker/claim", headers=c.student_headers, json=claim_body(c))
    ).status_code == 401
    assert (
        await c.post(
            f"/api/v1/ai/browser/classrooms/{c.session.id}/captures", headers=c.teacher_headers, json={"consent": True}
        )
    ).status_code == 403
    capture = await BrowserCapture.first()
    capture.expires_at = wall(utc_now()) - timedelta(seconds=1)
    await capture.save()
    assert (
        await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=claim_body(c))
    ).status_code == 410
    r = await c.post(f"/api/v1/ai/browser/captures/{capture.capture_id}/renew", headers=c.student_headers, json={})
    assert r.status_code == 410
    assert (await BrowserCapture.first()).owner_id is None
    r = await c.put(manage, headers=c.admin_headers, json={"enabled": False, "revision": c.job["generation"]})
    assert r.status_code == 200 and not r.json()["data"]["enabled"]


async def test_unscheduled_and_strict_consent(ai_client, monkeypatch):
    c = ai_client
    await prepare(c, monkeypatch)
    await ScheduleUser.all().delete()
    assert (await c.get(f"/api/v1/ai/browser/classrooms/{c.session.id}", headers=c.student_headers)).status_code == 403
    assert (
        await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=claim_body(c))
    ).status_code == 410
    for consent in [False, 1, "true"]:
        assert (
            await c.post(
                f"/api/v1/ai/browser/classrooms/{c.session.id}/captures",
                headers=c.student_headers,
                json={"consent": consent},
            )
        ).status_code == 422


async def test_administrator_control_teacher_readonly_and_explicit_rbac(ai_client, monkeypatch):
    c = ai_client
    await prepare(c, monkeypatch)
    manage = f"/api/v1/ai/browser/manage/{c.session.id}"
    admin = await c.get(manage, headers=c.admin_headers)
    teacher = await c.get(manage, headers=c.teacher_headers)
    assert admin.json()["data"]["can_configure"] is True
    assert teacher.json()["data"]["can_configure"] is False
    payload = {"enabled": False, "revision": admin.json()["data"]["revision"]}
    for headers in [c.teacher_headers, c.student_headers]:
        assert (await c.put(manage, headers=headers, json=payload)).status_code == 403
    # 误授 API 权限仍不能把教师变成管理员。
    permission = await Api.get(path="/api/v1/ai/browser/manage/{session_id}", method="PUT")
    teacher_role = await Role.get(name="TEACHER")
    await teacher_role.apis.add(permission)
    assert (await c.put(manage, headers=c.teacher_headers, json=payload)).status_code == 403
    other = await User.create(username="foreign-teacher", email="foreign@example.com", password="unused")
    await other.roles.add(teacher_role)
    assert (await c.get(manage, headers={"token": _make_token(other)})).status_code == 403
    # ADMIN 也必须具备动态路径 RBAC 授权；不能只测 superuser。
    admin_role = await Role.get(name="ADMIN")
    await admin_role.apis.remove(permission)
    assert (await c.put(manage, headers=c.admin_headers, json=payload)).status_code == 403
    await admin_role.apis.add(permission)
    stopped = await c.put(manage, headers=c.admin_headers, json=payload)
    assert stopped.status_code == 200 and stopped.json()["data"]["enabled"] is False
    assert stopped.json()["data"]["can_configure"] is True
    assert (await BrowserCapture.first()).owner_id is None


async def test_password_change_clears_camera_authorization(ai_client, monkeypatch):
    from app.controllers.user import user_controller

    c = ai_client
    await prepare(c, monkeypatch)
    await user_controller.set_password(c.student, "ChangedCamera123")
    assert (await BrowserCapture.first()).owner_id is None
    assert (
        await c.post("/api/v1/ai/browser/worker/claim", headers=c.device_headers, json=claim_body(c))
    ).status_code == 410
    assert (await c.get(f"/api/v1/ai/browser/classrooms/{c.session.id}", headers=c.student_headers)).status_code == 401
