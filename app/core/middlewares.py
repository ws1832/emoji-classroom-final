import re
from datetime import datetime

from fastapi.responses import Response
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.dependency import AuthControl
from app.models.admin import AuditLog

from .bgtask import BgTasks


class SimpleBaseMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        response = await self.before_request(request) or self.app
        await response(request.scope, request.receive, send)
        await self.after_request(request)

    async def before_request(self, request: Request):
        if request.url.path.startswith("/api/v1/ai/"):
            request.state.request_args = {"metadata_only": True}
            return
        return self.app

    async def after_request(self, request: Request):
        return None


class BackGroundTaskMiddleware(SimpleBaseMiddleware):
    async def before_request(self, request):
        await BgTasks.init_bg_tasks_obj()

    async def after_request(self, request):
        await BgTasks.execute_tasks()


class HttpAuditLogMiddleware(BaseHTTPMiddleware):
    """Audit operation metadata only; never parse or persist request/response bodies."""

    def __init__(self, app, methods: list[str], exclude_paths: list[str]):
        super().__init__(app)
        self.methods, self.exclude_paths = methods, exclude_paths

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = datetime.now()
        response = await call_next(request)
        if request.method not in self.methods or any(
            re.search(path, request.scope["path"], re.I) for path in self.exclude_paths
        ):
            return response
        data = {
            "path": request.scope["path"][:255],
            "status": response.status_code,
            "method": request.method,
            "response_time": int((datetime.now() - start).total_seconds() * 1000),
            "user_id": 0,
            "username": "",
            "request_args": {"metadata_only": True},
            "response_body": {"code": response.status_code, "msg": "Body omitted"},
        }
        route = request.scope.get("route")
        if isinstance(route, APIRoute):
            data.update(
                path=route.path,
                module=",".join(route.tags)[:64],
                summary=(route.summary or route.name or "")[:128],
            )
        token = request.headers.get("token")
        if token:
            try:
                user = await AuthControl.is_authed(token)
                data.update(user_id=user.id, username=user.username)
            except Exception:
                pass
        await AuditLog.create(**data)
        return response
