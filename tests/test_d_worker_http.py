"""显式真实视频→独立进程模型→HTTP→同一业务记录→看板/CSV验收。"""

import asyncio
import json
import os
import socket
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn

from app.models.ai import AIJob, AIReceipt
from app.models.classroom import EmojiRecord
from test_d_ai_api import ai_client as fixture_ai_client

ai_client = fixture_ai_client


@pytest.mark.skipif(
    not os.environ.get("AI_TEST_SMOKE_IMAGE"), reason="Explicit approved local image and model runtime required"
)
async def test_real_file_worker_to_http_dashboard_csv(ai_client, tmp_path):
    c = ai_client
    root = Path(__file__).resolve().parents[1]
    python = root / "ai-service/.venv/Scripts/python.exe"
    if not python.exists():
        python = Path(os.environ["AI_TEST_PYTHON"])
    image = str(Path(os.environ["AI_TEST_SMOKE_IMAGE"]).resolve())
    video = tmp_path / "input.avi"
    make_video = await asyncio.create_subprocess_exec(
        str(python),
        "-c",
        "import cv2,sys; im=cv2.imread(sys.argv[1]); assert im is not None; "
        "w=cv2.VideoWriter(sys.argv[2],cv2.VideoWriter_fourcc(*'MJPG'),2,(im.shape[1],im.shape[0])); "
        "assert w.isOpened(); [w.write(im) for _ in range(80)]; w.release()",
        image,
        str(video),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await make_video.communicate()
    assert make_video.returncode == 0
    device = (
        await c.post(
            "/api/v1/ai/devices",
            headers=c.admin_headers,
            json={
                "name": "http-file-smoke",
                "source_alias": "file",
                "teacher_ids": [c.teacher.id],
            },
        )
    ).json()["data"]
    credential = (
        await c.post(f"/api/v1/ai/devices/{device['id']}/credentials", headers=c.admin_headers, json={})
    ).json()["data"]
    created = await c.post(
        "/api/v1/ai/jobs",
        headers=c.admin_headers,
        json={
            "request_id": str(uuid4()),
            "session_id": c.session.id,
            "device_id": device["id"],
            "profile": "edge",
            "threshold": 0.0,
            "sample_interval": 0.5,
        },
    )
    assert created.status_code == 200
    job = created.json()["data"]
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(c._transport.app, log_level="error", lifespan="off"))
    server.install_signal_handlers = lambda: None
    server_task = asyncio.create_task(server.serve(sockets=[sock]))
    config = tmp_path / "worker.json"
    config.write_text(
        json.dumps(
            {
                "backend_url": f"http://127.0.0.1:{port}/api/v1",
                "profile": "edge",
                "manifest": str(root / "ai-service/models/manifest.json"),
                "model_dir": str(root / "ai-service/models"),
                "outbox_path": str(tmp_path / "outbox.sqlite3"),
                "sources": {"file": {"kind": "file", "value": str(video)}},
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["AI_DEVICE_TOKEN"] = credential["token"]
    process = None

    async def wait_for(predicate, seconds=30):
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            if await predicate():
                return
            await asyncio.sleep(0.2)
        raise AssertionError("Real worker gate timed out")

    async def ready():
        return (await AIJob.get(id=job["id"])).observed == "ready"

    async def records():
        return await EmojiRecord.filter(session_id=c.session.id, source="AI").count() >= 2

    async def stopped():
        return (await AIJob.get(id=job["id"])).active_slot is None

    try:
        while not server.started:
            await asyncio.sleep(0.05)
        process = await asyncio.create_subprocess_exec(
            str(python),
            "-m",
            "emoji_ai.worker",
            "--config",
            str(config),
            "--duration",
            "25",
            env=env,
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await wait_for(ready)
        start = await c.post(
            f"/api/v1/ai/jobs/{job['id']}/actions",
            headers=c.admin_headers,
            json={"action": "start", "revision": job["generation"]},
        )
        assert start.status_code == 200, start.text
        await wait_for(records)
        current = await AIJob.get(id=job["id"])
        stop = await c.post(
            f"/api/v1/ai/jobs/{job['id']}/actions",
            headers=c.admin_headers,
            json={"action": "stop", "revision": current.generation},
        )
        assert stop.status_code == 200
        await wait_for(stopped)
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr.decode(errors="replace").replace(credential["token"], "[redacted]")
        assert credential["token"].encode() not in stdout + stderr
        count = await EmojiRecord.filter(session_id=c.session.id).count()
        assert await AIReceipt.all().count() == count
        assert await EmojiRecord.filter(user_id__not_isnull=True).count() == 0
        dashboard = (
            await c.get("/api/v1/dashboard/realtime", headers=c.teacher_headers, params={"session_id": c.session.id})
        ).json()["data"]
        assert dashboard["ai_count"] == count and dashboard["student_count"] == 0
        csv = await c.get("/api/v1/emoji/export", headers=c.teacher_headers, params={"session_id": c.session.id})
        assert csv.status_code == 200 and len(csv.text.splitlines()) == count + 1
        assert "AI" in csv.text and "file" in csv.text
    finally:
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        server.should_exit = True
        await server_task
        sock.close()
