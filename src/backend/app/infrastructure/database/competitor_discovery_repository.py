"""竞品候选发现上下文和人工 Gate 的项目隔离仓储。"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    AgentArtifactModel,
    CompetitorCandidateDecisionModel,
    ProjectModel,
    SearchDiscoveryRunModel,
    SourceRequirementScopeModel,
)


class CompetitorDiscoveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def get_scope(self, project_id: str) -> SourceRequirementScopeModel | None:
        statement = select(SourceRequirementScopeModel).where(
            SourceRequirementScopeModel.project_id == project_id
        )
        return cast(SourceRequirementScopeModel | None, await self.session.scalar(statement))

    async def get_search_runs(
        self, project_id: str, run_ids: set[str]
    ) -> list[SearchDiscoveryRunModel]:
        if not run_ids:
            return []
        statement = select(SearchDiscoveryRunModel).where(
            SearchDiscoveryRunModel.project_id == project_id,
            SearchDiscoveryRunModel.search_discovery_run_id.in_(run_ids),
        )
        return list(await self.session.scalars(statement))

    async def get_artifact(
        self, project_id: str, artifact_id: str
    ) -> AgentArtifactModel | None:
        statement = select(AgentArtifactModel).where(
            AgentArtifactModel.project_id == project_id,
            AgentArtifactModel.artifact_id == artifact_id,
        )
        return cast(AgentArtifactModel | None, await self.session.scalar(statement))

    async def add_decision(self, decision: CompetitorCandidateDecisionModel) -> None:
        self.session.add(decision)
        await self.session.flush()

    async def get_decision(
        self, project_id: str, artifact_id: str
    ) -> CompetitorCandidateDecisionModel | None:
        statement = select(CompetitorCandidateDecisionModel).where(
            CompetitorCandidateDecisionModel.project_id == project_id,
            CompetitorCandidateDecisionModel.artifact_id == artifact_id,
        )
        return cast(
            CompetitorCandidateDecisionModel | None, await self.session.scalar(statement)
        )

    async def get_decisions(
        self, project_id: str, artifact_ids: set[str]
    ) -> list[CompetitorCandidateDecisionModel]:
        if not artifact_ids:
            return []
        statement = select(CompetitorCandidateDecisionModel).where(
            CompetitorCandidateDecisionModel.project_id == project_id,
            CompetitorCandidateDecisionModel.artifact_id.in_(artifact_ids),
        )
        return list(await self.session.scalars(statement))

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
