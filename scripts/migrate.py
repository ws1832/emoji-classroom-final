"""单一部署迁移入口；API 副本用 AUTO_INIT_DB=false，只读检查迁移状态。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tortoise import Tortoise
from app.core.init_app import init_data


async def main():
    try:
        await init_data()
        print("Database migrations and incremental permissions are ready.")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
