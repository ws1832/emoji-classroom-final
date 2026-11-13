from fastapi.exceptions import (
    HTTPException,
    RequestValidationError,
    ResponseValidationError,
)
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from tortoise.exceptions import DoesNotExist, IntegrityError


class SettingNotFound(Exception):
    pass


async def DoesNotExistHandle(req: Request, exc: DoesNotExist) -> JSONResponse:
    content = dict(code=404, msg="资源不存在", data=None)
    return JSONResponse(content=content, status_code=404)


async def IntegrityHandle(_: Request, exc: IntegrityError) -> JSONResponse:
    content = dict(code=409, msg="数据冲突，请刷新后重试", data=None)
    return JSONResponse(content=content, status_code=409)


async def HttpExcHandle(_: Request, exc: HTTPException) -> JSONResponse:
    content = dict(code=exc.status_code, msg=exc.detail, data=None)
    return JSONResponse(content=content, status_code=exc.status_code, headers=exc.headers)


async def RequestValidationHandle(req: Request, exc: RequestValidationError) -> JSONResponse:
    if req.url.path.startswith("/api/v1/ai/"):
        return JSONResponse({"code": 422, "msg": "Invalid AI metadata", "data": None}, status_code=422)
    # 不含input/ctx/异常文本，密码和未知字段中的secret均不可回显。
    content = dict(code=422, msg="请求参数校验失败", data=None)
    return JSONResponse(content=content, status_code=422)


async def ResponseValidationHandle(_: Request, exc: ResponseValidationError) -> JSONResponse:
    content = dict(code=500, msg="响应生成失败", data=None)
    return JSONResponse(content=content, status_code=500)
