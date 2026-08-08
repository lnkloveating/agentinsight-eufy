"""项目隔离的搜索发现运行仓储。"""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import SearchDiscoveryRunModel


class SearchDiscoveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, model: SearchDiscoveryRunModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def get_by_project(
        self, project_id: str, search_discovery_run_id: str
    ) -> SearchDiscoveryRunModel | None:
        statement = select(SearchDiscoveryRunModel).where(
            SearchDiscoveryRunModel.project_id == project_id,
            SearchDiscoveryRunModel.search_discovery_run_id == search_discovery_run_id,
        )
        return cast(SearchDiscoveryRunModel | None, await self.session.scalar(statement))

    async def list_by_project(
        self, project_id: str, *, limit: int
    ) -> tuple[list[SearchDiscoveryRunModel], int]:
        statement = (
            select(SearchDiscoveryRunModel)
            .where(SearchDiscoveryRunModel.project_id == project_id)
            .order_by(SearchDiscoveryRunModel.created_at.desc())
            .limit(limit)
        )
        models = list(await self.session.scalars(statement))
        total_statement = select(func.count()).select_from(SearchDiscoveryRunModel).where(
            SearchDiscoveryRunModel.project_id == project_id
        )
        total = int(await self.session.scalar(total_statement) or 0)
        return models, total

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
