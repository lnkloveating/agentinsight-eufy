"""竞品资料发现、Gate 与来源血缘的项目隔离仓储。"""

from typing import cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    CollectionJobModel,
    CompetitorMaterialDecisionModel,
    CompetitorMaterialDiscoveryItemModel,
    CompetitorMaterialDiscoveryModel,
    CompetitorMaterialSelectionModel,
    ProjectEventModel,
    ProjectModel,
    SourceAssetModel,
    SourceRequirementScopeModel,
)


class CompetitorMaterialDiscoveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def get_scope(self, project_id: str) -> SourceRequirementScopeModel | None:
        statement = select(SourceRequirementScopeModel).where(
            SourceRequirementScopeModel.project_id == project_id
        )
        return cast(SourceRequirementScopeModel | None, await self.session.scalar(statement))

    @staticmethod
    def _loaded(
        statement: Select[tuple[CompetitorMaterialDiscoveryModel]],
    ) -> Select[tuple[CompetitorMaterialDiscoveryModel]]:
        return statement.options(
            selectinload(CompetitorMaterialDiscoveryModel.items).selectinload(
                CompetitorMaterialDiscoveryItemModel.search_run
            ),
            selectinload(CompetitorMaterialDiscoveryModel.decision)
            .selectinload(CompetitorMaterialDecisionModel.selections)
            .selectinload(CompetitorMaterialSelectionModel.source_asset),
        )

    async def get_discovery(
        self, project_id: str, material_discovery_id: str
    ) -> CompetitorMaterialDiscoveryModel | None:
        statement = select(CompetitorMaterialDiscoveryModel).where(
            CompetitorMaterialDiscoveryModel.project_id == project_id,
            CompetitorMaterialDiscoveryModel.material_discovery_id == material_discovery_id,
        )
        return cast(
            CompetitorMaterialDiscoveryModel | None,
            await self.session.scalar(self._loaded(statement)),
        )

    async def list_discoveries(
        self, project_id: str
    ) -> list[CompetitorMaterialDiscoveryModel]:
        statement = (
            select(CompetitorMaterialDiscoveryModel)
            .where(CompetitorMaterialDiscoveryModel.project_id == project_id)
            .order_by(
                CompetitorMaterialDiscoveryModel.created_at.desc(),
                CompetitorMaterialDiscoveryModel.material_discovery_id.desc(),
            )
        )
        return list(await self.session.scalars(self._loaded(statement)))

    async def get_source_by_hash(
        self, project_id: str, content_hash: str
    ) -> SourceAssetModel | None:
        statement = select(SourceAssetModel).where(
            SourceAssetModel.project_id == project_id,
            SourceAssetModel.kind == "link",
            SourceAssetModel.content_hash == content_hash,
        )
        return cast(SourceAssetModel | None, await self.session.scalar(statement))

    async def add(self, model: object) -> None:
        self.session.add(model)
        await self.session.flush()

    async def add_event(self, model: ProjectEventModel) -> None:
        self.session.add(model)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def add_source_asset(self, model: SourceAssetModel) -> None:
        await self.add(model)

    async def add_collection_job(self, model: CollectionJobModel) -> None:
        await self.add(model)
