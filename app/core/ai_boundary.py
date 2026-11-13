"""业务API JSON读取前字节/时间限制，含chunked请求，先于audit。"""

import asyncio
import json
from time import monotonic

from starlette.responses import JSONResponse


class AIBoundaryMiddleware:
    def __init__(self, app, limit=256 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
            return await self.app(scope, receive, send)
        pairs = scope.get("headers", [])
        headers = dict(pairs)
        if scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)

        async def error(code, msg):
            await JSONResponse({"code": code, "msg": msg, "data": None}, code)(scope, receive, send)

        if sum(key.lower() == b"content-length" for key, _ in pairs) > 1:
            return await error(400, "Ambiguous Content-Length")
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await error(400, "Invalid Content-Length")
        if length < 0 or length > self.limit:
            return await error(413, "API request exceeds byte limit")
        content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
        # 无正文动作接口无需Content-Type；所有有正文写操作只接受JSON。
        if content_type != b"application/json" and (length or b"transfer-encoding" in headers):
            return await error(415, "API requires JSON metadata")
        chunks, size = [], 0
        deadline = monotonic() + 10
        while True:
            try:
                message = await asyncio.wait_for(receive(), max(0, deadline - monotonic()))
            except asyncio.TimeoutError:
                return await error(408, "Request body timeout")
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                return await error(413, "API request exceeds byte limit")
            chunks.append(chunk)
            if not message.get("more_body"):
                break
        body = b"".join(chunks)
        if body and content_type != b"application/json":
            return await error(415, "API requires JSON")
        try:
            if body and not isinstance(json.loads(body), dict):
                raise ValueError()
        except (ValueError, UnicodeError, RecursionError):
            return await error(422, "Invalid JSON metadata")
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
