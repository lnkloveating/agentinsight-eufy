"""创建可供前端使用的中文 eufy 演示项目。"""

# ruff: noqa: E402

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "src" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.application.events import ProjectEventBroker
from app.core.config import get_settings
from app.infrastructure.database import Database
from app.infrastructure.database.seeds import seed_eufy_demo


async def seed() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    broker = ProjectEventBroker()
    await database.create_schema()
    try:
        project_id = await seed_eufy_demo(database, broker)
    finally:
        await database.dispose()
    print(f"演示项目已准备完成：{project_id}")


if __name__ == "__main__":
    asyncio.run(seed())
