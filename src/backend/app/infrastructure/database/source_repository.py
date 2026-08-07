"""原始资料资产的项目隔离仓储。"""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    CollectionJobModel,
    ProjectModel,
    SourceAssetModel,
)


class SourceAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def project_exists(self, project_id: str) -> bool:
        return await self.session.get(ProjectModel, project_id) is not None

    async def add_collection_job(self, job: CollectionJobModel) -> None:
        self.session.add(job)
        await self.session.flush()

    async def add_source_asset(self, asset: SourceAssetModel) -> None:
        self.session.add(asset)
        await self.session.flush()

    async def get_collection_job(
        self, collection_job_id: str
    ) -> CollectionJobModel | None:
        return await self.session.get(CollectionJobModel, collection_job_id)

    async def get_by_project(
        self, project_id: str, source_asset_id: str
    ) -> SourceAssetModel | None:
        statement = select(SourceAssetModel).where(
            SourceAssetModel.project_id == project_id,
            SourceAssetModel.source_asset_id == source_asset_id,
        )
        return cast(SourceAssetModel | None, await self.session.scalar(statement))

    async def get_by_hash(
        self, project_id: str, kind: str, content_hash: str
    ) -> SourceAssetModel | None:
        statement = select(SourceAssetModel).where(
            SourceAssetModel.project_id == project_id,
            SourceAssetModel.kind == kind,
            SourceAssetModel.content_hash == content_hash,
        )
        return cast(SourceAssetModel | None, await self.session.scalar(statement))

    async def list_assets(
        self,
        project_id: str,
        *,
        cursor: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> tuple[list[SourceAssetModel], str | None, int]:
        filters = [SourceAssetModel.project_id == project_id]
        if kind is not None:
            filters.append(SourceAssetModel.kind == kind)
        if status is not None:
            filters.append(SourceAssetModel.status == status)
        total = int(
            await self.session.scalar(
                select(func.count(SourceAssetModel.source_asset_id)).where(*filters)
            )
            or 0
        )
        page_filters = list(filters)
        if cursor is not None:
            page_filters.append(SourceAssetModel.source_asset_id > cursor)
        models = list(
            await self.session.scalars(
                select(SourceAssetModel)
                .where(*page_filters)
                .order_by(SourceAssetModel.source_asset_id.asc())
                .limit(limit + 1)
            )
        )
        has_more = len(models) > limit
        items = models[:limit]
        next_cursor = items[-1].source_asset_id if has_more and items else None
        return items, next_cursor, total

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
