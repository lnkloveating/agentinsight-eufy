"""资料范围和准备度评估所需的项目隔离查询。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    CollectionJobModel,
    EvidenceModel,
    ProjectModel,
    SourceAssetModel,
    SourceRequirementScopeModel,
    SourceRoutingModel,
)


class SourceRequirementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def get_scope(self, project_id: str) -> SourceRequirementScopeModel | None:
        statement = select(SourceRequirementScopeModel).where(
            SourceRequirementScopeModel.project_id == project_id
        )
        return await self.session.scalar(statement)

    async def add_scope(self, scope: SourceRequirementScopeModel) -> None:
        self.session.add(scope)
        await self.session.flush()

    async def list_assets(self, project_id: str) -> list[SourceAssetModel]:
        statement = (
            select(SourceAssetModel)
            .where(
                SourceAssetModel.project_id == project_id,
                SourceAssetModel.status == "ready",
            )
            .order_by(SourceAssetModel.source_asset_id.asc())
        )
        return list(await self.session.scalars(statement))

    async def list_routings(self, project_id: str) -> list[SourceRoutingModel]:
        statement = (
            select(SourceRoutingModel)
            .where(
                SourceRoutingModel.project_id == project_id,
                SourceRoutingModel.status == "confirmed",
            )
            .order_by(SourceRoutingModel.source_asset_id.asc())
        )
        return list(await self.session.scalars(statement))

    async def list_eligible_evidence(self, project_id: str) -> list[EvidenceModel]:
        statement = (
            select(EvidenceModel)
            .where(
                EvidenceModel.project_id == project_id,
                EvidenceModel.status.in_(("verified", "partially_verified")),
            )
            .order_by(EvidenceModel.evidence_id.asc())
        )
        return list(await self.session.scalars(statement))

    async def list_collection_jobs(self, project_id: str) -> list[CollectionJobModel]:
        statement = (
            select(CollectionJobModel)
            .where(CollectionJobModel.project_id == project_id)
            .order_by(CollectionJobModel.collection_job_id.asc())
        )
        return list(await self.session.scalars(statement))

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
