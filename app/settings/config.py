import os
import typing
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from pathlib import Path
from app.utils.password import is_password_strong


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    VERSION: str = "0.1.0"
    APP_TITLE: str = "表情符号课堂情绪检查器"
    PROJECT_NAME: str = "Emoji Classroom"
    APP_DESCRIPTION: str = "学生手动反馈与匿名 AI 表情采集、课堂看板和管理统计服务"

    CORS_ORIGINS: typing.List = ["http://localhost:3100", "http://127.0.0.1:3100"]
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: typing.List = ["*"]
    CORS_ALLOW_HEADERS: typing.List = ["*"]

    DEBUG: bool = True
    AUTO_INIT_DB: bool = True
    BOOTSTRAP_ADMIN_PASSWORD: str = "123456"
    BOOTSTRAP_ADMIN_PASSWORD_FILE: str | None = None
    SECRET_KEY_FILE: str | None = None
    MYSQL_PASSWORD_FILE: str | None = None
    # 独立浏览器推理服务身份，由管理员部署一次，学生不会获得其设备凭证。
    AI_BROWSER_DEVICE_ID: int | None = None
    AI_BROWSER_UPLOAD_URL: str = "/ai-stream/frames"

    PROJECT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    BASE_DIR: str = os.path.abspath(os.path.join(PROJECT_ROOT, os.pardir))
    LOGS_ROOT: str = os.path.join(BASE_DIR, "app/logs")
    SECRET_KEY: str = (
        "3488a63e1765035d386f05409663f55c83bfae3b3c61a932744b20ad14244dcf"  # 生产环境请替换为随机生成的密钥
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # JWT 登录有效期：7 天

    # 默认使用 MySQL；本地开发、测试和部署时可以通过 .env 文件覆盖以下配置。
    # 如果暂时没有 MySQL，可以将 DB_ENGINE 修改为 sqlite。
    DB_ENGINE: Literal["mysql", "sqlite"] = "mysql"
    MYSQL_HOST: str = "127.0.0.1"  # MySQL 地址；本机数据库通常使用 127.0.0.1
    MYSQL_PORT: int = 3306  # MySQL 端口；默认端口为 3306
    MYSQL_USER: str = "root"  # 请在 .env 中修改为自己的 MySQL 用户名
    MYSQL_PASSWORD: str = ""  # 请在 .env 中修改为自己的 MySQL 密码，禁止把真实密码提交到代码仓库
    MYSQL_DATABASE: str = "emoji_classroom"  # 请在 .env 中修改为自己创建的数据库名称
    MYSQL_CHARSET: str = "utf8mb4"  # 支持中文和 Emoji 的字符集
    SQLITE_PATH: str | None = None

    @model_validator(mode="after")
    def load_secret_files(self):
        for field in ("SECRET_KEY", "MYSQL_PASSWORD", "BOOTSTRAP_ADMIN_PASSWORD"):
            path = getattr(self, field + "_FILE")
            if path:
                setattr(self, field, Path(path).read_text(encoding="utf-8").strip())
        if not self.DEBUG and (
            len(self.SECRET_KEY) < 32
            or self.SECRET_KEY == type(self).model_fields["SECRET_KEY"].default
            or not is_password_strong(self.BOOTSTRAP_ADMIN_PASSWORD)
        ):
            raise ValueError("Production requires a private SECRET_KEY and BOOTSTRAP_ADMIN_PASSWORD")
        if not self.DEBUG and ("*" in self.CORS_ORIGINS or not self.CORS_ORIGINS):
            raise ValueError("Production requires explicit CORS_ORIGINS")
        return self

    @property
    def TORTOISE_ORM(self) -> dict:
        if self.DB_ENGINE == "sqlite":
            return {
                "connections": {
                    "sqlite": {
                        "engine": "tortoise.backends.sqlite",
                        "credentials": {"file_path": self.SQLITE_PATH or f"{self.BASE_DIR}/db.sqlite3"},
                    }
                },
                "apps": {
                    "models": {
                        "models": ["app.models", "aerich.models"],
                        "default_connection": "sqlite",
                    }
                },
                "use_tz": False,
                "timezone": "Asia/Shanghai",
            }

        return {
            "connections": {
                "mysql": {
                    "engine": "tortoise.backends.mysql",
                    "credentials": {
                        "host": self.MYSQL_HOST,
                        "port": self.MYSQL_PORT,
                        "user": self.MYSQL_USER,
                        "password": self.MYSQL_PASSWORD,
                        "database": self.MYSQL_DATABASE,
                        "charset": self.MYSQL_CHARSET,
                    },
                }
            },
            "apps": {
                "models": {
                    "models": ["app.models", "aerich.models"],
                    "default_connection": "mysql",
                }
            },
            "use_tz": False,  # 使用不带时区的时间，和现有项目保持一致
            "timezone": "Asia/Shanghai",  # 数据库时间使用上海时区
        }

    DATETIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"


settings = Settings()
