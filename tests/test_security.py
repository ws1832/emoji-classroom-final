"""安全测试：弱密码、SQL 注入与 CSV 公式注入防护。"""

import pytest
import jwt
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.api.v1.base import base_router
from app.api.v1.courses import courses_router
from app.api.v1.emoji import emoji_router
from app.api.v1.sessions import sessions_router
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
from app.models import User, AuditLog, Role
from app.services.export import build_csv
from app.utils.password import get_password_hash
from app.settings import settings
from app.utils.jwt_utils import credential_tag
from app.core.middlewares import HttpAuditLogMiddleware
from app.core.ai_boundary import AIBoundaryMiddleware
from app.core.init_app import init_menus
from app.models import Menu
from app.api.v1.users import users_router
from app.api.v1.roles import roles_router
from app.api.v1.auditlog import auditlog_router


def _register_exceptions(app: FastAPI) -> None:
    app.add_exception_handler(DoesNotExist, DoesNotExistHandle)
    app.add_exception_handler(HTTPException, HttpExcHandle)
    app.add_exception_handler(IntegrityError, IntegrityHandle)
    app.add_exception_handler(RequestValidationError, RequestValidationHandle)
    app.add_exception_handler(ResponseValidationError, ResponseValidationHandle)


@pytest.fixture
async def client(tmp_path):
    """独立的 SQLite 测试库，挂载认证、课程、课堂和 Emoji 路由。"""

    config = {
        "connections": {
            "default": {
                "engine": "tortoise.backends.sqlite",
                "credentials": {"file_path": str(tmp_path / "security_test.sqlite3")},
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

    student = await User.create(
        username="student",
        email="student@example.com",
        password=get_password_hash("Student123"),
        is_active=True,
        is_superuser=False,
    )

    app = FastAPI(title="emoji-classroom-security-test")
    _register_exceptions(app)
    # 强制记录所有路径，验证敏感信息保护不依赖exclude配置。
    app.add_middleware(HttpAuditLogMiddleware, methods=["GET", "POST", "PUT", "DELETE"], exclude_paths=[])
    app.add_middleware(AIBoundaryMiddleware)
    app.include_router(base_router, prefix="/api/v1/base")
    app.include_router(courses_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(emoji_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1/user")
    app.include_router(roles_router, prefix="/api/v1/role")
    app.include_router(auditlog_router, prefix="/api/v1/auditlog")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        test_client.student = student
        yield test_client

    await Tortoise.close_connections()


# ---------- 弱密码 ----------


async def test_register_rejects_weak_passwords(client):
    for weak in ["password", "12345678", "pass", "abcdefgh"]:
        resp = await client.post(
            "/api/v1/base/register",
            json={"username": "weak", "email": f"weak-{weak}@example.com", "password": weak},
        )
        assert resp.status_code == 422, f"weak password accepted: {weak!r}"


async def test_register_accepts_strong_password_and_logs_in(client):
    resp = await client.post(
        "/api/v1/base/register",
        json={"username": "strong", "email": "strong@example.com", "password": "Passw0rd123"},
    )
    assert resp.status_code == 200

    resp = await client.post("/api/v1/base/access_token", json={"username": "strong", "password": "Passw0rd123"})
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    info = await client.get("/api/v1/base/userinfo", headers={"token": token})
    assert "STUDENT" in info.json()["data"]["role_codes"]


async def test_teacher_registration_assigns_teacher_role(client):
    resp = await client.post(
        "/api/v1/base/register-teacher",
        json={"username": "teacher2", "email": "teacher2@example.com", "password": "Teacher123"},
    )
    assert resp.status_code == 200

    resp = await client.post("/api/v1/base/access_token", json={"username": "teacher2", "password": "Teacher123"})
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    info = await client.get("/api/v1/base/userinfo", headers={"token": token})
    assert "TEACHER" in info.json()["data"]["role_codes"]


async def test_user_no_uses_independent_per_role_sequence(client):
    first = await client.post(
        "/api/v1/base/register",
        json={"username": "first", "email": "first@example.com", "password": "Student123"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["user_no"] == "PB0001"

    second = await client.post(
        "/api/v1/base/register",
        json={"username": "second", "email": "second@example.com", "password": "Student123"},
    )
    assert second.status_code == 200
    assert second.json()["data"]["user_no"] == "PB0002"

    teacher = await client.post(
        "/api/v1/base/register-teacher",
        json={"username": "seqteacher", "email": "seqteacher@example.com", "password": "Teacher123"},
    )
    assert teacher.status_code == 200
    assert teacher.json()["data"]["user_no"] == "TB0001"


async def test_update_password_rejects_weak_password(client):
    resp = await client.post("/api/v1/base/access_token", json={"username": "student", "password": "Student123"})
    token = resp.json()["data"]["access_token"]

    resp = await client.post(
        "/api/v1/base/update_password",
        json={"old_password": "Student123", "new_password": "allletters"},
        headers={"token": token},
    )
    assert resp.status_code == 422


# ---------- SQL 注入 ----------


async def test_sql_injection_login_does_not_authenticate(client):
    resp = await client.post(
        "/api/v1/base/access_token",
        json={"username": "student' OR '1'='1", "password": "whatever1"},
    )
    assert resp.status_code == 400


async def test_sql_injection_user_id_param_is_rejected(client):
    login = await client.post("/api/v1/base/access_token", json={"username": "student", "password": "Student123"})
    token = login.json()["data"]["access_token"]

    resp = await client.get(
        "/api/v1/emoji/history",
        params={"user_id": "1 OR 1=1"},
        headers={"token": token},
    )
    # 参数类型为 int，注入字符串会在查询执行前被校验拒绝。
    assert resp.status_code == 422


async def test_sql_injection_in_login_username_not_found(client):
    resp = await client.post(
        "/api/v1/base/access_token",
        json={"username": "'; DROP TABLE user", "password": "whatever1"},
    )
    # 注入字符串被当作普通用户名处理，未匹配到账号即拒绝登录。
    assert resp.status_code == 400


# ---------- CSV 公式注入 ----------


def test_csv_formula_injection_is_neutralized():
    content = build_csv(
        ["device_source", "username"],
        [["=cmd|' /C calc'!A0", '=HYPERLINK("http://evil")'], ["normal", "ok"]],
    )
    assert "'=cmd" in content
    assert "'=HYPERLINK" in content
    # 普通值不应被错误加前缀。
    assert "normal" in content


async def login(client, username="student", password="Student123"):
    result = await client.post("/api/v1/base/access_token", json={"username": username, "password": password})
    assert result.status_code == 200, result.text
    return {"token": result.json()["data"]["access_token"]}


async def test_audit_omits_passwords_tokens_and_unknown_input(client):
    headers = await login(client)
    secret = "do-not-reflect-this-private-input"
    rejected = await client.post(
        "/api/v1/base/register",
        json={"username": "rejected", "email": "bad", "password": secret},
    )
    assert rejected.status_code == 422 and secret not in rejected.text
    logs = await AuditLog.all()
    assert logs
    contents = str([(log.request_args, log.response_body) for log in logs])
    for value in [secret, "Student123", headers["token"]]:
        assert value not in contents
    assert all(log.request_args == {"metadata_only": True} for log in logs)


async def test_jwt_requires_expiry_and_strict_identity(client):
    base = {"user_id": client.student.id, "credential_tag": credential_tag(client.student.password), "exp": 4102444800}
    for payload in [
        {k: v for k, v in base.items() if k != "exp"},
        {k: v for k, v in base.items() if k != "credential_tag"},
        {**base, "user_id": str(client.student.id)},
        {**base, "user_id": True},
        {**base, "credential_tag": "wrong"},
        {**base, "credential_tag": "密" * 64},
        {**base, "exp": None},
        {**base, "exp": float("inf")},
    ]:
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        response = await client.get("/api/v1/base/userinfo", headers={"token": token})
        assert response.status_code == 401
    assert (await client.get("/api/v1/base/userinfo")).status_code == 401


async def test_password_change_revokes_old_jwt(client):
    headers = await login(client)
    changed = await client.post(
        "/api/v1/base/update_password",
        headers=headers,
        json={"old_password": "Student123", "new_password": "ChangedPass987"},
    )
    assert changed.status_code == 200
    assert (await client.get("/api/v1/base/userinfo", headers=headers)).status_code == 401
    fresh = await login(client, password="ChangedPass987")
    assert (await client.get("/api/v1/base/userinfo", headers=fresh)).status_code == 200


async def test_administrator_creation_reset_and_superuser_boundaries(client):
    # 隔离router无DependPermission也必须拥有ADMIN业务角色。
    headers = await login(client)
    for path in ["/api/v1/user/list", "/api/v1/role/list", "/api/v1/auditlog/list"]:
        assert (await client.get(path, headers=headers)).status_code == 403
    admin = await User.create(
        username="admin-review", email="admin-review@example.com", password=get_password_hash("AdminReview123")
    )
    role = await Role.create(name="ADMIN")
    await admin.roles.add(role)
    admin_headers = await login(client, "admin-review", "AdminReview123")
    payload = {"username": "new-user", "email": "new-user@example.com", "password": "123456"}
    assert (await client.post("/api/v1/user/create", headers=admin_headers, json=payload)).status_code == 422
    assert (
        await client.post(
            "/api/v1/user/create",
            headers=admin_headers,
            json={**payload, "password": "StrongPass123", "is_superuser": True},
        )
    ).status_code == 403
    reset = await client.post("/api/v1/user/reset_password", headers=admin_headers, json={"user_id": client.student.id})
    assert reset.status_code == 200 and reset.headers["cache-control"] == "no-store"
    password = reset.json()["data"]["temporary_password"]
    assert password != "123456" and len(password) >= 24
    assert (await client.get("/api/v1/base/userinfo", headers=headers)).status_code == 401
    await login(client, password=password)
    assert all(password not in str(log.request_args) + str(log.response_body) for log in await AuditLog.all())
    superuser = await User.create(username="root-review", email="root-review@example.com", is_superuser=True)
    assert (
        await client.post(
            "/api/v1/user/update",
            headers=admin_headers,
            json={"id": superuser.id, "username": superuser.username, "email": superuser.email},
        )
    ).status_code == 403
    assert (
        await client.delete("/api/v1/user/delete", headers=admin_headers, params={"user_id": superuser.id})
    ).status_code == 403


async def test_all_business_writes_are_bounded_before_parsing(client):
    response = await client.post(
        "/api/v1/base/access_token",
        headers={"Content-Length": str(256 * 1024 + 1), "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    response = await client.post("/api/v1/base/register", content=b'{"large":"' + b"x" * (256 * 1024) + b'"}')
    assert response.status_code == 413
    for body in [b"[]", b'"value"', b"\xff", b"[" * 1100]:
        response = await client.post(
            "/api/v1/base/access_token", content=body, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    response = await client.post("/api/v1/base/access_token", content="username=student&password=example")
    assert response.status_code == 415


async def test_system_menus_are_completed_without_erasing_existing_customizations(client):
    custom = await Menu.create(name="自定义菜单", path="/custom", parent_id=0, component="/custom")
    await init_menus()
    parent = await Menu.get(path="/system", parent_id=0)
    user_menu = await Menu.get(parent_id=parent.id, path="user")
    user_menu.name = "自定义用户管理名称"
    await user_menu.save()
    await Menu.filter(parent_id=parent.id, path="role").delete()
    await init_menus()
    await init_menus()
    assert await Menu.filter(id=custom.id).exists()
    assert await Menu.filter(parent_id=parent.id).count() == 3
    assert (await Menu.get(id=user_menu.id)).name == "自定义用户管理名称"
