import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from aerich import Command
from tortoise import Tortoise

from app.models import ClassSession, Course, EmojiRecord, User
from scripts.backup_sqlite import backup
from app.settings.config import Settings


def test_production_settings_require_private_secrets_and_support_files(tmp_path):
    with pytest.raises(ValueError):
        Settings(_env_file=None, DEBUG=False)
    key = tmp_path / "key"
    password = tmp_path / "password"
    key.write_text("x" * 64, encoding="utf-8")
    password.write_text("Private-bootstrap-123", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        DEBUG=False,
        SECRET_KEY_FILE=str(key),
        BOOTSTRAP_ADMIN_PASSWORD_FILE=str(password),
    )
    assert settings.SECRET_KEY == "x" * 64
    assert settings.BOOTSTRAP_ADMIN_PASSWORD == "Private-bootstrap-123"
    with pytest.raises(ValueError):
        Settings(_env_file=None, DEBUG=False, SECRET_KEY="x" * 64, BOOTSTRAP_ADMIN_PASSWORD="allletters")
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            DEBUG=False,
            SECRET_KEY="x" * 64,
            BOOTSTRAP_ADMIN_PASSWORD="Private-bootstrap-123",
            CORS_ORIGINS=["*"],
        )


@pytest.mark.parametrize("existing", [False, True])
async def test_aerich_fresh_upgrade_and_online_backup_restore(tmp_path, existing):
    path = tmp_path / "operations.sqlite3"
    config = {
        "connections": {"default": {"engine": "tortoise.backends.sqlite", "credentials": {"file_path": str(path)}}},
        "apps": {"models": {"models": ["app.models", "aerich.models"], "default_connection": "default"}},
        "use_tz": False,
        "timezone": "Asia/Shanghai",
    }
    root = Path(__file__).resolve().parents[1]
    try:
        command = Command(tortoise_config=config, location=str(root / "migrations"))
        await command.init()
        if existing:
            await command._upgrade(Tortoise.get_connection("default"), "0_20261031000000_init.py")
            await command._upgrade(Tortoise.get_connection("default"), "1_20261031202616_classroom_emotion_models.py")
        else:
            await command.upgrade()
        user = await User.create(username="backup", email="backup@example.com")
        from app.core.ai_auth import utc_now, wall

        now = wall(utc_now())
        course = await Course.create(name="backup", teacher_id=user.id)
        session = await ClassSession.create(course_id=course.id, start_time=now, end_time=now + timedelta(hours=1))
        record = await EmojiRecord.create(user_id=user.id, session_id=session.id, emoji_type="HAPPY", source="MANUAL")
        await command.upgrade()
        assert await command.heads() == []
        assert await EmojiRecord.all().count() == 1
        backup(path, tmp_path / "snapshot.sqlite3")
        with sqlite3.connect(tmp_path / "snapshot.sqlite3") as restored:
            assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert restored.execute("SELECT id FROM emoji_record").fetchone()[0] == record.id
            assert restored.execute("SELECT count(*) FROM aerich").fetchone()[0] == 4
        with pytest.raises(ValueError):
            backup(path, tmp_path / "snapshot.sqlite3")
    finally:
        await Tortoise.close_connections()
