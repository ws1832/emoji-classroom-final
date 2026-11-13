import asyncio
import json
import os
import socket
from datetime import timedelta
from pathlib import Path

import pytest
import uvicorn

from app.api.v1.base import base_router
from app.api.v1.sessions import sessions_router
from app.api.v1.users import users_router
from app.api.v1.roles import roles_router
from app.core.dependency import DependPermission
from app.core.init_app import init_roles, init_menus
from app.core.ai_auth import utc_now, wall
from app.models import ClassSession, Course, Menu
from app.utils.password import get_password_hash
from test_d_ai_api import ai_client as fixture_ai_client
from test_d_browser_capture import prepare

ai_client = fixture_ai_client


@pytest.mark.skipif(
    not os.environ.get("AI_TEST_BROWSER_PYTHON"), reason="Explicit isolated Playwright runtime required"
)
async def test_browser_admin_teacher_student(ai_client, monkeypatch):
    c = ai_client
    await prepare(c, monkeypatch)
    await c.post(f"/api/v1/ai/browser/captures/{c.capture['capture_id']}/stop", headers=c.student_headers, json={})
    app = c._transport.app
    app.include_router(base_router, prefix="/api/v1/base")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1/user", dependencies=[DependPermission])
    app.include_router(roles_router, prefix="/api/v1/role", dependencies=[DependPermission])
    await init_menus()
    parent = await Menu.get(path="/classroom", parent_id=0)
    for name, path in [("AI服务身份", "ai-devices"), ("课堂采集管理", "ai-jobs")]:
        await Menu.get_or_create(
            parent_id=parent.id,
            path=path,
            defaults={
                "name": name,
                "menu_type": "menu",
                "component": f"/classroom/{path}",
                "keepalive": False,
            },
        )
    await init_roles()
    password = "Browser-isolated-123"
    for user in (c.admin, c.teacher, c.student):
        user.password = get_password_hash(password)
        await user.save()
    course = await Course.create(name="foreign", teacher_id=c.admin.id)
    now = wall(utc_now())
    foreign = await ClassSession.create(
        course_id=course.id, start_time=now - timedelta(minutes=1), end_time=now + timedelta(hours=1)
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    server.install_signal_handlers = lambda: None
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            await asyncio.sleep(0.05)
        env = os.environ.copy()
        env["AI_BROWSER_TEST_CONFIG"] = json.dumps(
            {
                "api_url": f"http://127.0.0.1:{sock.getsockname()[1]}",
                "web_url": os.environ.get("AI_TEST_WEB_URL", "http://localhost:3100"),
                "admin": c.admin.username,
                "teacher": c.teacher.username,
                "student": c.student.username,
                "password": password,
                "teacher_id": c.teacher.id,
                "session_id": c.session.id,
                "foreign_session_id": foreign.id,
            }
        )
        process = await asyncio.create_subprocess_exec(
            os.environ["AI_TEST_BROWSER_PYTHON"],
            str(Path(__file__).resolve().parents[1] / "web/tests/ai-browser.py"),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 120)
        except asyncio.TimeoutError:
            process.terminate()
            await process.wait()
            raise
        assert process.returncode == 0, stderr.decode(errors="replace")
        assert b"passed" in stdout
    finally:
        server.should_exit = True
        await task
        sock.close()
