"""启动 Brief 审批后的真实研究任务并同步项目状态。"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.application.events import ProjectEventBroker
from app.application.research.user_research import UserResearchService
from app.infrastructure.database.models import AgentRunModel, ProjectEventModel, ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.project import AgentRunStatus, ProjectStatus


class InitialResearchOrchestrator:
    """把 Brief 审批连接到当前已实现的真实 User Research Agent。"""

    def __init__(
        self,
        database: Database,
        user_research: UserResearchService,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.user_research = user_research
        self.event_broker = event_broker
        self.trace_id = trace_id
        self._guard = asyncio.Lock()
        self._running_projects: set[str] = set()

    async def run(self, project_id: str) -> None:
        async with self._guard:
            if project_id in self._running_projects:
                return
            self._running_projects.add(project_id)
        try:
            try:
                await self._prepare_retry(project_id)
                artifact = await self.user_research.run(project_id)
            except Exception as exc:
                await self._finish_manager(
                    project_id,
                    status=AgentRunStatus.FAILED,
                    progress=100,
                    message="用户调研 Agent 执行失败。",
                    error_message=str(exc),
                    project_status=ProjectStatus.FAILED,
                )
                return

            await self._finish_manager(
                project_id,
                status=(
                    AgentRunStatus.COMPLETED
                    if artifact.status == "completed"
                    else AgentRunStatus.PARTIAL
                ),
                progress=100,
                message="用户调研已完成，结果已保存。",
                project_status=ProjectStatus.RESEARCHING,
                progress_value=30,
            )
        finally:
            async with self._guard:
                self._running_projects.discard(project_id)

    async def _prepare_retry(self, project_id: str) -> None:
        """Restore a failed project before a user-triggered research retry."""
        now = datetime.now(UTC)
        async with self.database.session() as session:
            repository = ProjectRepository(session)
            project = await repository.get_project(project_id)
            if project is None or project.status != ProjectStatus.FAILED.value:
                return

            project.status = ProjectStatus.RESEARCHING.value
            project.current_stage = "research_planning"
            project.progress = 30
            project.updated_at = now

            runs = await repository.list_agent_runs(project_id)
            manager = next((run for run in runs if run.agent_type == "research_manager"), None)
            if manager is not None:
                manager.status = AgentRunStatus.RUNNING
                manager.progress = 5
                manager.message = "Brief 已通过，正在重新启动研究任务。"
                manager.error_code = None
                manager.error_message = None
                manager.started_at = now
                manager.completed_at = None

            await repository.add_event(
                ProjectEventModel(
                    event_id=f"evt_{uuid4().hex[:16]}",
                    project_id=project_id,
                    sequence_number=0,
                    event_type="project_status_changed",
                    data_json={
                        "previous_status": ProjectStatus.FAILED.value,
                        "status": ProjectStatus.RESEARCHING.value,
                        "current_stage": project.current_stage,
                        "progress": project.progress,
                        "action": "retry_research",
                    },
                    trace_id=self.trace_id,
                    created_at=now,
                )
            )
            await repository.commit()
        await self.event_broker.notify(project_id)

    async def stale_project_ids(self) -> list[str]:
        """返回进程重启前停在初始 Running 状态的项目。"""
        async with self.database.session() as session:
            statement = (
                select(ProjectModel.project_id)
                .join(AgentRunModel, AgentRunModel.project_id == ProjectModel.project_id)
                .where(
                    ProjectModel.status == ProjectStatus.RESEARCHING.value,
                    AgentRunModel.agent_type == "research_manager",
                    AgentRunModel.status == AgentRunStatus.RUNNING.value,
                    AgentRunModel.progress <= 5,
                )
            )
            result = await session.scalars(statement)
            return list(result)

    async def _finish_manager(
        self,
        project_id: str,
        *,
        status: AgentRunStatus,
        progress: int,
        message: str,
        error_message: str | None = None,
        project_status: ProjectStatus,
        progress_value: int | None = None,
    ) -> None:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            repository = ProjectRepository(session)
            project = await repository.get_project(project_id)
            if project is None:
                return
            runs = await repository.list_agent_runs(project_id)
            manager = next(
                (run for run in runs if run.agent_type == "research_manager"),
                None,
            )
            if manager is None:
                return

            manager.status = status
            manager.progress = progress
            manager.message = message
            manager.error_message = error_message
            manager.completed_at = now
            project.status = project_status.value
            if progress_value is not None:
                project.progress = max(project.progress, progress_value)
            project.updated_at = now
            event = ProjectEventModel(
                event_id=f"evt_{uuid4().hex[:16]}",
                project_id=project_id,
                sequence_number=0,
                event_type=("agent_completed" if status in {AgentRunStatus.COMPLETED, AgentRunStatus.PARTIAL} else "agent_failed"),
                data_json={
                    "agent_run_id": manager.agent_run_id,
                    "agent_type": manager.agent_type,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "error_message": error_message,
                },
                trace_id=self.trace_id,
                created_at=now,
            )
            await repository.add_event(event)
            await repository.commit()
        await self.event_broker.notify(project_id)
