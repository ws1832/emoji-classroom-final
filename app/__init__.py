from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import HTTPException
from tortoise import Tortoise
from aerich import Command

from app.core.exceptions import SettingNotFound
from app.core.init_app import (
    init_data,
    make_middlewares,
    register_exceptions,
    register_routers,
)

try:
    from app.settings.config import settings
except ImportError:
    raise SettingNotFound("Can not import settings")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时准备数据库和基础权限数据；关闭时释放连接。
    if settings.AUTO_INIT_DB:
        await init_data()
    else:
        command = Command(tortoise_config=settings.TORTOISE_ORM)
        await command.init()
        if await command.heads():
            await Tortoise.close_connections()
            raise RuntimeError("Database migration required; run scripts/migrate.py once before API startup")
    yield
    await Tortoise.close_connections()


def create_app() -> FastAPI:
    # 在工厂函数中统一组装中间件、异常处理和 API 路由，便于测试和部署。
    app = FastAPI(
        title=settings.APP_TITLE,
        description=settings.APP_DESCRIPTION,
        version=settings.VERSION,
        openapi_url="/openapi.json",
        middleware=make_middlewares(),
        lifespan=lifespan,
    )
    register_exceptions(app)
    register_routers(app, prefix="/api")

    @app.get("/healthz", include_in_schema=False)
    async def health():
        try:
            await Tortoise.get_connection(settings.DB_ENGINE).execute_query("SELECT 1")
        except Exception:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ready"}

    return app


app = create_app()
