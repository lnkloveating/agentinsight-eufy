"""统一资料路由的项目隔离仓储。"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import SourceRoutingModel


class SourceRoutingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, project_id: str, source_asset_id: str) -> SourceRoutingModel | None:
        statement = select(SourceRoutingModel).where(
            SourceRoutingModel.project_id == project_id,
            SourceRoutingModel.source_asset_id == source_asset_id,
        )
        return cast(SourceRoutingModel | None, await self.session.scalar(statement))

    async def add(self, routing: SourceRoutingModel) -> None:
        self.session.add(routing)
        await self.session.flush()

    async def confirmed_source_asset_ids(self, project_id: str, route: str) -> set[str]:
        statement = select(SourceRoutingModel).where(
            SourceRoutingModel.project_id == project_id,
            SourceRoutingModel.status == "confirmed",
        )
        records = list(await self.session.scalars(statement))
        return {
            record.source_asset_id for record in records if route in record.confirmed_routes_json
        }

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
