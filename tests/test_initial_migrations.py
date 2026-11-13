"""Verify checked-in migrations bootstrap a fresh SQLite database."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest


MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations" / "models"


async def _upgrade_sql(path: Path) -> str:
    spec = importlib.util.spec_from_file_location("migration_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return await module.upgrade(None)


@pytest.mark.parametrize("classroom_tables_exist", [False, True])
async def test_initial_migrations_create_admin_and_classroom_tables(tmp_path, classroom_tables_exist):
    migrations = sorted(MIGRATION_DIR.glob("[01]_*.py"))
    assert len(migrations) == 2
    scripts = [await _upgrade_sql(path) for path in migrations]

    with sqlite3.connect(tmp_path / "bootstrap.sqlite3") as connection:
        # A failed pre-fix startup may already have created classroom tables.
        if classroom_tables_exist:
            connection.executescript(scripts[1])
        for script in scripts:
            connection.executescript(script)

        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "aerich",
            "user",
            "role",
            "menu",
            "api",
            "auditlog",
            "dept",
            "user_role",
            "role_menu",
            "role_api",
            "course",
            "class_session",
            "schedule_user",
            "emoji_record",
        } <= tables
        user_columns = {row[1] for row in connection.execute('PRAGMA table_info("user")')}
        assert "user_no" in user_columns
