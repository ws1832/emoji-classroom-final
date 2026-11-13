"""显式 MySQL 8 integration gate；凭证由环境传入，不跳过后冒充通过。"""

import asyncio
import importlib.util
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import asyncmy
import pytest
from tortoise import Tortoise, connections

from app.core.ai_auth import DeviceIdentity, utc_now, wall, wire
from app.models import ClassSession, Course, User
from app.models.ai import AIReceipt
from app.models.classroom import EmojiRecord
from app.schemas.ai import DeviceCreate, JobAction, JobCreate, WorkerAck, WorkerHeartbeat, AIIngestEvent
from app.services import ai_jobs
from app.services.ai_ingest import ingest_event


@pytest.mark.skipif(not os.environ.get("AI_TEST_MYSQL_PASSWORD"), reason="Explicit temporary MySQL instance required")
@pytest.mark.parametrize("existing", [False, True])
async def test_mysql_additive_migration_and_concurrent_effect(existing):
    root = Path(__file__).resolve().parents[1]
    password = os.environ["AI_TEST_MYSQL_PASSWORD"]
    port = int(os.environ.get("AI_TEST_MYSQL_PORT", "3307"))
    database = "ai_test_" + uuid4().hex[:12]
    raw = await asyncmy.connect(host="127.0.0.1", port=port, user="root", password=password, autocommit=True)
    async with raw.cursor() as cur:
        await cur.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
    config = {
        "connections": {
            "default": {
                "engine": "tortoise.backends.mysql",
                "credentials": {
                    "host": "127.0.0.1",
                    "port": port,
                    "user": "root",
                    "password": password,
                    "database": database,
                },
            }
        },
        "apps": {"models": {"models": ["app.models", "aerich.models"], "default_connection": "default"}},
        "use_tz": False,
        "timezone": "Asia/Shanghai",
    }
    try:
        await Tortoise.init(config=config)
        db = connections.get("default")
        # ORM-compatible baseline new/old paths; existing path keeps a MANUAL record.
        await db.execute_script((root / "database/mysql_orm_bootstrap.sql").read_text(encoding="utf-8"))
        user = await User.create(username="mysql-admin", email="mysql-admin@example.com", is_superuser=True)
        teacher = await User.create(username="mysql-teacher", email="mysql-teacher@example.com")
        course = await Course.create(name="mysql", teacher_id=teacher.id)
        now = wall(utc_now())
        session = await ClassSession.create(
            course_id=course.id, start_time=now - timedelta(minutes=1), end_time=now + timedelta(minutes=10)
        )
        if existing:
            await EmojiRecord.create(session_id=session.id, user_id=teacher.id, emoji_type="HAPPY", source="MANUAL")
        path = root / "migrations/models/2_20261111180000_ai_control.py"
        spec = importlib.util.spec_from_file_location("migration_ai", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        await db.execute_script(await migration.upgrade(db))
        from aerich import Command
        command = Command(tortoise_config=config, location=str(root / "migrations"))
        await command.init()
        assert len(await command.upgrade()) == 4
        assert await EmojiRecord.all().count() == int(existing)
        device = await ai_jobs.create_device(
            user, DeviceCreate(name="mysql-camera", source_alias="camera", teacher_ids=[teacher.id])
        )
        cred = await ai_jobs.issue_credential(user, device["id"], 90)
        identity = DeviceIdentity(cred["credential_id"], device["id"])
        incarnation = uuid4()
        await ai_jobs.heartbeat(identity, WorkerHeartbeat(incarnation=incarnation, profiles=["edge"]))
        job = await ai_jobs.create_job(
            user, JobCreate(request_id=uuid4(), session_id=session.id, device_id=device["id"])
        )
        await ai_jobs.acknowledge(
            identity, job["id"], WorkerAck(incarnation=incarnation, generation=job["generation"], observed="ready")
        )
        await ai_jobs.control_job(user, job["id"], JobAction(action="start", revision=job["generation"]))
        beat = await ai_jobs.heartbeat(identity, WorkerHeartbeat(incarnation=incarnation, profiles=["edge"]))
        job = beat["jobs"][0]
        event = AIIngestEvent.model_validate(
            {
                "event_id": str(uuid4()),
                "job_id": job["id"],
                "lease_id": job["lease_id"],
                "generation": job["generation"],
                "captured_at": wire(wall(utc_now())),
                "emoji_type": "HAPPY",
                "confidence": 0.95,
                "model_version": job["model_version"],
                "config_revision": 1,
                "quality": {"detection_confidence": 0.95},
            }
        )
        responses = await asyncio.gather(*[ingest_event(identity, event) for _ in range(5)])
        assert sum(row["status"] == "accepted" for row in responses) == 1
        assert await AIReceipt.all().count() == 1
        assert await EmojiRecord.all().count() == 1 + int(existing)
        from app.services.statistics import get_statistics, get_realtime_dashboard

        aggregate = await get_statistics(teacher.id, False)
        assert aggregate["overview"]["total_records"] == 1 + int(existing)
        assert aggregate["by_day"] == [{"day": now.strftime("%Y-%m-%d"), "count": 1 + int(existing)}]
        dashboard = await get_realtime_dashboard(teacher.id, False, session.id)
        assert dashboard["ai_count"] == 1 and dashboard["student_count"] == int(existing)
        from aerich import Command

        command = Command(tortoise_config=config, location=str(root / "migrations"))
        await command.init()
        assert await command.upgrade() == []
        assert await command.heads() == []
        assert await EmojiRecord.all().count() == 1 + int(existing)
        # 可选本机真实 mysqldump→新库 restore，不把文档命令当验收。
        if os.environ.get("AI_TEST_MYSQL_BIN"):
            from asyncmy.constants import CLIENT
            binary = Path(os.environ["AI_TEST_MYSQL_BIN"]) / ("mysqldump.exe" if os.name == "nt" else "mysqldump")
            env = os.environ.copy()
            env["MYSQL_PWD"] = password
            process = await asyncio.create_subprocess_exec(
                str(binary), "--host=127.0.0.1", f"--port={port}", "--user=root",
                "--single-transaction", "--no-tablespaces", "--skip-comments", database,
                env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            dump, errors = await process.communicate()
            assert process.returncode == 0, errors.decode(errors="replace").replace(password, "[redacted]")
            restore_name = "ai_restore_" + uuid4().hex[:12]
            async with raw.cursor() as cur:
                await cur.execute(f"CREATE DATABASE `{restore_name}` CHARACTER SET utf8mb4")
            restored = None
            try:
                restored = await asyncmy.connect(
                    host="127.0.0.1", port=port, user="root", password=password,
                    database=restore_name, autocommit=True, client_flag=CLIENT.MULTI_STATEMENTS,
                )
                async with restored.cursor() as cur:
                    await cur.execute(dump.decode("utf-8"))
                    while await cur.nextset():
                        pass
                    await cur.execute("SELECT count(*) FROM emoji_record")
                    assert (await cur.fetchone())[0] == 1 + int(existing)
                    await cur.execute("SELECT count(*) FROM ai_receipt")
                    assert (await cur.fetchone())[0] == 1
                    await cur.execute("SELECT count(*) FROM aerich")
                    assert (await cur.fetchone())[0] == 4
            finally:
                if restored:
                    await restored.ensure_closed()
                async with raw.cursor() as cur:
                    await cur.execute(f"DROP DATABASE `{restore_name}`")
    finally:
        await Tortoise.close_connections()
        async with raw.cursor() as cur:
            await cur.execute(f"DROP DATABASE `{database}`")
        await raw.ensure_closed()
