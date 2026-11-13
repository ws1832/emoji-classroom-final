"""pytest 共享 fixtures：SQLite 测试库、种子用户和测试客户端。"""

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
from app.models import User
from app.schemas.login import JWTPayload
from app.utils.jwt_utils import create_access_token, credential_tag


def _register_exceptions(app: FastAPI) -> None:
    # 与 app/core/init_app.py 保持一致，避免测试结果和线上异常格式不一致。
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
    """为每个测试准备独立的 SQLite 数据库和已登录的教师/学生。"""

    config = {
        "connections": {
            "default": {
                "engine": "tortoise.backends.sqlite",
                "credentials": {"file_path": str(tmp_path / "test.sqlite3")},
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

    teacher = await User.create(
        username="teacher",
        email="teacher@example.com",
        password="not-used",
        is_active=True,
        is_superuser=False,
    )
    student = await User.create(
        username="student",
        email="student@example.com",
        password="not-used",
        is_active=True,
        is_superuser=False,
    )

    app = FastAPI(title="emoji-classroom-test")
    _register_exceptions(app)
    app.include_router(courses_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(emoji_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(statistics_router, prefix="/api/v1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        test_client.teacher = teacher
        test_client.student = student
        test_client.teacher_token = _make_token(teacher)
        test_client.student_token = _make_token(student)
        yield test_client

    await Tortoise.close_connections()
