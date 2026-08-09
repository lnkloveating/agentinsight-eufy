"""竞品候选来源接入的项目隔离仓储。"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    AgentArtifactModel,
    CollectionJobModel,
    CompetitorCandidateDecisionModel,
    CompetitorSourceOnboardingItemModel,
    CompetitorSourceOnboardingModel,
    ProjectModel,
    SourceAssetModel,
    SourceRequirementScopeModel,
)


class CompetitorSourceOnboardingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def get_artifact(
        self, project_id: str, artifact_id: str
    ) -> AgentArtifactModel | None:
        statement = select(AgentArtifactModel).where(
            AgentArtifactModel.project_id == project_id,
            AgentArtifactModel.artifact_id == artifact_id,
        )
        return cast(AgentArtifactModel | None, await self.session.scalar(statement))

    async def get_decision(
        self, project_id: str, artifact_id: str
    ) -> CompetitorCandidateDecisionModel | None:
        statement = select(CompetitorCandidateDecisionModel).where(
            CompetitorCandidateDecisionModel.project_id == project_id,
            CompetitorCandidateDecisionModel.artifact_id == artifact_id,
        )
        return cast(
            CompetitorCandidateDecisionModel | None,
            await self.session.scalar(statement),
        )

    async def get_scope(self, project_id: str) -> SourceRequirementScopeModel | None:
        statement = select(SourceRequirementScopeModel).where(
            SourceRequirementScopeModel.project_id == project_id
        )
        return cast(SourceRequirementScopeModel | None, await self.session.scalar(statement))

    async def get_source_by_hash(
        self, project_id: str, content_hash: str
    ) -> SourceAssetModel | None:
        statement = select(SourceAssetModel).where(
            SourceAssetModel.project_id == project_id,
            SourceAssetModel.kind == "link",
            SourceAssetModel.content_hash == content_hash,
        )
        return cast(SourceAssetModel | None, await self.session.scalar(statement))

    async def get_onboarding_by_artifact(
        self, project_id: str, artifact_id: str
    ) -> CompetitorSourceOnboardingModel | None:
        statement = (
            select(CompetitorSourceOnboardingModel)
            .where(
                CompetitorSourceOnboardingModel.project_id == project_id,
                CompetitorSourceOnboardingModel.artifact_id == artifact_id,
            )
            .options(
                selectinload(CompetitorSourceOnboardingModel.items).selectinload(
                    CompetitorSourceOnboardingItemModel.source_asset
                )
            )
        )
        return cast(
            CompetitorSourceOnboardingModel | None,
            await self.session.scalar(statement),
        )

    async def list_onboardings(
        self, project_id: str
    ) -> list[CompetitorSourceOnboardingModel]:
        statement = (
            select(CompetitorSourceOnboardingModel)
            .where(CompetitorSourceOnboardingModel.project_id == project_id)
            .options(
                selectinload(CompetitorSourceOnboardingModel.items).selectinload(
                    CompetitorSourceOnboardingItemModel.source_asset
                )
            )
            .order_by(
                CompetitorSourceOnboardingModel.created_at.desc(),
                CompetitorSourceOnboardingModel.onboarding_id.desc(),
            )
        )
        return list(await self.session.scalars(statement))

    async def add_collection_job(self, model: CollectionJobModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def add_source_asset(self, model: SourceAssetModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def add_onboarding(self, model: CompetitorSourceOnboardingModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def add_item(self, model: CompetitorSourceOnboardingItemModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
