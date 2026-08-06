"""项目创建、查询和人工审批用例。"""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.events.broker import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.models import (
    AgentRunModel,
    DecisionModel,
    ProjectEventModel,
    ProjectModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.project import (
    AgentRun,
    AgentRunStatus,
    DecisionAction,
    DecisionCreate,
    PendingDecision,
    Project,
    ProjectCreate,
    ProjectStatus,
    ResearchBrief,
)


class ProjectService:
    """处理不依赖 LLM 的确定性项目生命周期规则。"""

    def __init__(
        self,
        repository: ProjectRepository,
        trace_id: str,
        event_broker: ProjectEventBroker,
    ) -> None:
        self.repository = repository
        self.trace_id = trace_id
        self.event_broker = event_broker

    async def create_project(self, payload: ProjectCreate) -> Project:
        project_id = f"proj_{uuid4().hex[:16]}"
        decision_id = f"decision_{uuid4().hex[:16]}"
        now = datetime.now(UTC)
        pending_decision = PendingDecision(
            decision_id=decision_id,
            gate="brief",
            allowed_actions=[
                DecisionAction.APPROVE,
                DecisionAction.REVISE,
                DecisionAction.TERMINATE,
            ],
        )
        project_model = ProjectModel(
            project_id=project_id,
            status=ProjectStatus.AWAITING_BRIEF_APPROVAL,
            current_stage="brief_confirmation",
            progress=5,
            brief_json=payload.brief.model_dump(mode="json"),
            pending_decision_json=pending_decision.model_dump(mode="json"),
            created_at=now,
            updated_at=now,
        )
        manager_run = AgentRunModel(
            agent_run_id=f"run_{uuid4().hex[:16]}",
            project_id=project_id,
            agent_type="research_manager",
            agent_name="调研总管 Agent",
            status=AgentRunStatus.WAITING,
            progress=0,
            message="等待研究 Brief 审批。",
        )
        created_event = ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type="project_created",
            data_json={
                "status": ProjectStatus.AWAITING_BRIEF_APPROVAL,
                "current_stage": "brief_confirmation",
                "progress": 5,
                "message": "研究项目已创建，等待确认 Brief。",
            },
            trace_id=self.trace_id,
            created_at=now,
        )

        try:
            await self.repository.add_project(project_model)
            await self.repository.add_agent_run(manager_run)
            await self.repository.add_event(created_event)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.event_broker.notify(project_id)
        return self._to_project(project_model)

    async def list_projects(self) -> list[Project]:
        return [self._to_project(model) for model in await self.repository.list_projects()]

    async def get_project(self, project_id: str) -> Project:
        return self._to_project(await self._require_project(project_id))

    async def list_agent_runs(self, project_id: str) -> list[AgentRun]:
        await self._require_project(project_id)
        models = await self.repository.list_agent_runs(project_id)
        return [self._to_agent_run(model) for model in models]

    async def submit_decision(self, project_id: str, payload: DecisionCreate) -> Project:
        project = await self._require_project(project_id)
        pending = project.pending_decision_json
        if pending is None:
            raise AppError(
                code="PROJECT_NOT_WAITING_FOR_DECISION",
                message="当前项目没有等待处理的人工审批。",
                status_code=409,
                details={"project_id": project_id, "status": project.status},
            )
        if payload.decision_id != pending.get("decision_id"):
            raise AppError(
                code="DECISION_ID_MISMATCH",
                message="审批编号与项目当前等待的审批不一致。",
                status_code=409,
                details={"expected_decision_id": pending.get("decision_id")},
            )

        allowed_actions = set(pending.get("allowed_actions", []))
        if payload.action not in allowed_actions:
            raise AppError(
                code="DECISION_ACTION_NOT_ALLOWED",
                message="当前审批节点不允许该操作。",
                status_code=409,
                details={"allowed_actions": sorted(allowed_actions)},
            )

        previous_status = ProjectStatus(project.status)
        next_status, next_stage, progress = self._transition(previous_status, payload.action)
        now = datetime.now(UTC)
        project.status = next_status
        project.current_stage = next_stage
        project.progress = progress
        project.pending_decision_json = None
        project.updated_at = now

        decision = DecisionModel(
            decision_record_id=f"decision_record_{uuid4().hex[:12]}",
            decision_id=payload.decision_id,
            project_id=project_id,
            gate=str(pending.get("gate", "unknown")),
            action=payload.action,
            reason=payload.reason,
            actor=payload.actor,
            selected_concept_ids_json=payload.selected_concept_ids,
            trace_id=self.trace_id,
            created_at=now,
        )
        event = ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type="project_status_changed",
            data_json={
                "previous_status": previous_status,
                "status": next_status,
                "current_stage": next_stage,
                "progress": progress,
                "action": payload.action,
                "actor": payload.actor,
                "reason": payload.reason,
            },
            trace_id=self.trace_id,
            created_at=now,
        )

        try:
            await self.repository.add_decision(decision)
            await self.repository.add_event(event)
            await self._activate_manager_if_needed(project_id, payload.action, now)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.event_broker.notify(project_id)
        return self._to_project(project)

    async def _activate_manager_if_needed(
        self,
        project_id: str,
        action: DecisionAction,
        now: datetime,
    ) -> None:
        if action is not DecisionAction.APPROVE:
            return
        runs = await self.repository.list_agent_runs(project_id)
        if not runs:
            return
        manager = runs[0]
        manager.status = AgentRunStatus.RUNNING
        manager.progress = 5
        manager.message = "Brief 已通过，正在规划调研任务。"
        manager.started_at = now
        event = ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type="agent_status_changed",
            data_json=self._to_agent_run(manager).model_dump(mode="json"),
            trace_id=self.trace_id,
            created_at=now,
        )
        await self.repository.add_event(event)

    async def _require_project(self, project_id: str) -> ProjectModel:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="没有找到指定的研究项目。",
                status_code=404,
                details={"project_id": project_id},
            )
        return project

    @staticmethod
    def _transition(
        status: ProjectStatus,
        action: DecisionAction,
    ) -> tuple[ProjectStatus, str, int]:
        transitions = {
            (ProjectStatus.AWAITING_BRIEF_APPROVAL, DecisionAction.APPROVE): (
                ProjectStatus.RESEARCHING,
                "research_planning",
                10,
            ),
            (ProjectStatus.AWAITING_BRIEF_APPROVAL, DecisionAction.REVISE): (
                ProjectStatus.DRAFT,
                "brief_revision",
                3,
            ),
            (ProjectStatus.AWAITING_BRIEF_APPROVAL, DecisionAction.TERMINATE): (
                ProjectStatus.TERMINATED,
                "terminated",
                5,
            ),
            (ProjectStatus.AWAITING_CONCEPT_APPROVAL, DecisionAction.APPROVE): (
                ProjectStatus.GENERATING_REPORT,
                "report_generation",
                80,
            ),
            (ProjectStatus.AWAITING_CONCEPT_APPROVAL, DecisionAction.RESEARCH_MORE): (
                ProjectStatus.SUPPLEMENTING_RESEARCH,
                "supplementary_research",
                60,
            ),
            (ProjectStatus.AWAITING_CONCEPT_APPROVAL, DecisionAction.REJECT): (
                ProjectStatus.TERMINATED,
                "terminated",
                70,
            ),
            (ProjectStatus.AWAITING_FINAL_APPROVAL, DecisionAction.APPROVE): (
                ProjectStatus.COMPLETED,
                "completed",
                100,
            ),
            (ProjectStatus.AWAITING_FINAL_APPROVAL, DecisionAction.REVISE): (
                ProjectStatus.GENERATING_REPORT,
                "report_revision",
                90,
            ),
            (ProjectStatus.AWAITING_FINAL_APPROVAL, DecisionAction.TERMINATE): (
                ProjectStatus.TERMINATED,
                "terminated",
                95,
            ),
        }
        result = transitions.get((status, action))
        if result is None:
            raise AppError(
                code="INVALID_PROJECT_TRANSITION",
                message="当前项目状态不能执行该审批操作。",
                status_code=409,
                details={"status": status, "action": action},
            )
        return result

    @staticmethod
    def _to_project(model: ProjectModel) -> Project:
        return Project(
            project_id=model.project_id,
            status=ProjectStatus(model.status),
            current_stage=model.current_stage,
            progress=model.progress,
            brief=ResearchBrief.model_validate(model.brief_json),
            pending_decision=(
                PendingDecision.model_validate(model.pending_decision_json)
                if model.pending_decision_json is not None
                else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_agent_run(model: AgentRunModel) -> AgentRun:
        return AgentRun(
            agent_run_id=model.agent_run_id,
            project_id=model.project_id,
            task_id=model.task_id,
            agent_type=model.agent_type,
            agent_name=model.agent_name,
            status=AgentRunStatus(model.status),
            progress=model.progress,
            quality_score=model.quality_score,
            message=model.message,
            evidence_ids=model.evidence_ids_json,
            unknowns=model.unknowns_json,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_code=model.error_code,
            error_message=model.error_message,
        )
