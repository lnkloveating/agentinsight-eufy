"""项目生命周期数据库仓储。"""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    AgentRunModel,
    DecisionModel,
    ProjectEventModel,
    ProjectModel,
)


class ProjectRepository:
    """集中管理项目、Agent、事件和审批的持久化操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_project(self, project: ProjectModel) -> None:
        self.session.add(project)
        await self.session.flush()

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def list_projects(self) -> list[ProjectModel]:
        statement: Select[tuple[ProjectModel]] = select(ProjectModel).order_by(
            ProjectModel.updated_at.desc()
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def add_agent_run(self, agent_run: AgentRunModel) -> None:
        self.session.add(agent_run)
        await self.session.flush()

    async def list_agent_runs(self, project_id: str) -> list[AgentRunModel]:
        statement: Select[tuple[AgentRunModel]] = (
            select(AgentRunModel)
            .where(AgentRunModel.project_id == project_id)
            .order_by(AgentRunModel.agent_run_id.asc())
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def get_agent_run(self, agent_run_id: str) -> AgentRunModel | None:
        return await self.session.get(AgentRunModel, agent_run_id)

    async def add_event(self, event: ProjectEventModel) -> None:
        event.sequence_number = await self.next_event_sequence(event.project_id)
        self.session.add(event)
        await self.session.flush()

    async def list_events(
        self,
        project_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[ProjectEventModel]:
        statement: Select[tuple[ProjectEventModel]] = (
            select(ProjectEventModel)
            .where(
                ProjectEventModel.project_id == project_id,
                ProjectEventModel.sequence_number > after_sequence,
            )
            .order_by(ProjectEventModel.sequence_number.asc())
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def get_event_sequence(self, project_id: str, event_id: str) -> int | None:
        statement = select(ProjectEventModel.sequence_number).where(
            ProjectEventModel.project_id == project_id,
            ProjectEventModel.event_id == event_id,
        )
        sequence = await self.session.scalar(statement)
        return int(sequence) if sequence is not None else None

    async def next_event_sequence(self, project_id: str) -> int:
        statement = select(func.coalesce(func.max(ProjectEventModel.sequence_number), 0)).where(
            ProjectEventModel.project_id == project_id
        )
        current = await self.session.scalar(statement)
        return int(current or 0) + 1

    async def add_decision(self, decision: DecisionModel) -> None:
        self.session.add(decision)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def delete_project(self, project_id: str) -> None:
        project = await self.get_project(project_id)
        if project is not None:
            await self.session.delete(project)
            await self.session.flush()
