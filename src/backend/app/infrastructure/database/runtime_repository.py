"""Agent Runtime、版本化 Artifact 和运行血缘仓储。"""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import AgentArtifactModel, AgentRunModel, ProjectModel


class AgentRuntimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def project_exists(self, project_id: str) -> bool:
        return await self.session.get(ProjectModel, project_id) is not None

    async def add_run(self, run: AgentRunModel) -> None:
        self.session.add(run)
        await self.session.flush()

    async def get_run(self, agent_run_id: str) -> AgentRunModel | None:
        return await self.session.get(AgentRunModel, agent_run_id)

    async def next_attempt_number(self, project_id: str, task_id: str) -> int:
        statement = select(func.coalesce(func.max(AgentRunModel.attempt_number), 0)).where(
            AgentRunModel.project_id == project_id,
            AgentRunModel.task_id == task_id,
        )
        current = await self.session.scalar(statement)
        return int(current or 0) + 1

    async def add_artifact(self, artifact: AgentArtifactModel) -> None:
        self.session.add(artifact)
        await self.session.flush()

    async def next_artifact_version(
        self,
        project_id: str,
        task_id: str,
        artifact_type: str,
    ) -> int:
        statement = select(func.coalesce(func.max(AgentArtifactModel.version), 0)).where(
            AgentArtifactModel.project_id == project_id,
            AgentArtifactModel.task_id == task_id,
            AgentArtifactModel.artifact_type == artifact_type,
        )
        current = await self.session.scalar(statement)
        return int(current or 0) + 1

    async def get_artifact(self, artifact_id: str) -> AgentArtifactModel | None:
        return await self.session.get(AgentArtifactModel, artifact_id)

    async def get_artifacts_by_ids(self, artifact_ids: set[str]) -> list[AgentArtifactModel]:
        if not artifact_ids:
            return []
        statement = select(AgentArtifactModel).where(
            AgentArtifactModel.artifact_id.in_(artifact_ids)
        )
        return list(await self.session.scalars(statement))

    async def list_task_artifacts(
        self,
        project_id: str,
        task_id: str,
    ) -> list[AgentArtifactModel]:
        statement = (
            select(AgentArtifactModel)
            .where(
                AgentArtifactModel.project_id == project_id,
                AgentArtifactModel.task_id == task_id,
            )
            .order_by(AgentArtifactModel.version.asc())
        )
        return list(await self.session.scalars(statement))

    async def latest_artifact(
        self,
        project_id: str,
        task_id: str,
        artifact_type: str,
    ) -> AgentArtifactModel | None:
        statement = (
            select(AgentArtifactModel)
            .where(
                AgentArtifactModel.project_id == project_id,
                AgentArtifactModel.task_id == task_id,
                AgentArtifactModel.artifact_type == artifact_type,
            )
            .order_by(AgentArtifactModel.version.desc())
            .limit(1)
        )
        return cast(AgentArtifactModel | None, await self.session.scalar(statement))

    async def latest_project_artifact_by_type(
        self,
        project_id: str,
        artifact_type: str,
    ) -> AgentArtifactModel | None:
        statement = (
            select(AgentArtifactModel)
            .where(
                AgentArtifactModel.project_id == project_id,
                AgentArtifactModel.artifact_type == artifact_type,
            )
            .order_by(AgentArtifactModel.created_at.desc(), AgentArtifactModel.version.desc())
            .limit(1)
        )
        return cast(AgentArtifactModel | None, await self.session.scalar(statement))

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
