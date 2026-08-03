"""异步数据库连接与会话生命周期。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base


class Database:
    """封装 SQLAlchemy 引擎，便于测试和生产环境替换数据库。"""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if database_url.endswith(":memory:"):
            engine_options["poolclass"] = StaticPool

        self.engine = create_async_engine(database_url, **engine_options)
        self.session_factory = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_schema(self) -> None:
        """开发和测试环境自动创建表；生产环境使用 Alembic。"""
        self._ensure_sqlite_directory()
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """提供自动关闭的异步数据库会话。"""
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        """释放数据库连接。"""
        await self.engine.dispose()

    def _ensure_sqlite_directory(self) -> None:
        prefix = "sqlite+aiosqlite:///"
        if not self.database_url.startswith(prefix) or self.database_url.endswith(":memory:"):
            return
        database_path = Path(self.database_url.removeprefix(prefix))
        database_path.parent.mkdir(parents=True, exist_ok=True)
