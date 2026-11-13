"""只清理过期幂等回执，不删除 Emoji 业务记录；默认 dry-run，单次最多 500 条。"""

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tortoise import Tortoise
from app.core.ai_auth import utc_now, wall
from app.models.ai import AIReceipt
from app.settings.config import settings


async def cleanup(days=30, apply=False):
    if days < 1:
        raise ValueError("Retention must exceed the 15-minute replay window")
    ids = (
        await AIReceipt.filter(received_at__lt=wall(utc_now()) - timedelta(days=days))
        .order_by("id")
        .limit(500)
        .values_list("id", flat=True)
    )
    if apply and ids:
        await AIReceipt.filter(id__in=ids).delete()
    return {"eligible_batch": len(ids), "deleted": len(ids) if apply else 0}


async def main(args):
    await Tortoise.init(config=settings.TORTOISE_ORM)
    try:
        print(await cleanup(args.days, args.apply))
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
