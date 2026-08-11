"""Application service for evidence-bounded Technical Feasibility runs."""

from app.agents.technical_feasibility import (
    TechnicalFeasibilityArtifact,
    TechnicalFeasibilityContextBuilder,
    TechnicalFeasibilityRunCreate,
)
from app.application.runtime import (
    AgentRuntimeGateway,
    ArtifactStore,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.core.errors import AppError
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.session import Database
from app.infrastructure.database.source_recovery_repository import SourceRecoveryRepository
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)
from app.workflows.handoff import build_research_handoff

TECHNICAL_FEASIBILITY_TASK_ID = "task_technical_feasibility"


class TechnicalFeasibilityService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: TechnicalFeasibilityContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(
        self, project_id: str, request: TechnicalFeasibilityRunCreate
    ) -> TechnicalFeasibilityArtifact:
        project = await self._require_runnable_project(project_id)
        opportunity = await self.artifact_store.latest_by_type(
            project_id, ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value
        )
        if opportunity is None:
            raise AppError(
                code="TECHNICAL_FEASIBILITY_OPPORTUNITY_REQUIRED",
                message="必须先生成并审批生态机会，才能评估技术可行性。",
                status_code=409,
            )
        upstream_research = {}
        for agent_type in (
            ResearchAgentType.USER_RESEARCH,
            ResearchAgentType.COMPETITOR_RESEARCH,
        ):
            stored = await self.artifact_store.latest_by_type(project_id, agent_type.value)
            if stored is not None:
                upstream_research[agent_type.value] = stored.artifact
        handoff = build_research_handoff(upstream_research)
        previous = await self.artifact_store.list_versions(
            project_id, TECHNICAL_FEASIBILITY_TASK_ID
        )
        supplemental = await self._resolved_supplemental_evidence_ids(
            project_id, [item.artifact.artifact_id for item in previous]
        )
        bundle = await self.context_builder.build(
            project_id,
            handoff,
            opportunity.artifact,
            supplemental,
        )
        brief = ResearchBrief.model_validate(project.brief_json)
        task = ResearchTask(
            task_id=TECHNICAL_FEASIBILITY_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.TECHNICAL_FEASIBILITY,
            goal=(
                "逐项验证已审批生态机会所需的设备能力、数据、API、部署、延迟、隐私、权限"
                "与失败降级条件，并判断首个 Demo 的真实技术边界。"
            ),
            scope={
                "selected_opportunity_ids": request.selected_opportunity_ids,
                "device_capability_graph": bundle.capability_graph.model_dump(mode="json"),
            },
            required_artifacts=[
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
                "device_capability_graph",
            ],
            evidence_rules=EvidenceRules(citation_required=True),
            budget=ResearchBudget(
                max_pages=bundle.evidence_context.included_evidence_count,
                max_iterations=2,
                deadline_seconds=180,
            ),
            depends_on=[opportunity.artifact.task_id],
            acceptance_checks=[
                "每个所选机会均有独立技术评估",
                "现有能力判断来自 Device Capability Graph",
                "非 unknown 技术结论必须引用 Evidence",
                "最终 verdict 由后端确定性计算",
            ],
        )
        context = AgentContext(
            project_id=project_id,
            brief=brief,
            iteration=len(previous),
            upstream_artifacts={
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value: opportunity.artifact
            },
            selected_innovation_ids=request.selected_opportunity_ids,
            evidence_context=bundle.evidence_context,
            research_handoff=handoff,
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return TechnicalFeasibilityArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[TechnicalFeasibilityArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(
            project_id, TECHNICAL_FEASIBILITY_TASK_ID
        )
        return [
            TechnicalFeasibilityArtifact.from_research_artifact(item.artifact)
            for item in versions
        ]

    async def _resolved_supplemental_evidence_ids(
        self, project_id: str, artifact_ids: list[str]
    ) -> list[str]:
        evidence_ids: list[str] = []
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            for artifact_id in artifact_ids:
                for recovery in await repository.list_resolved_for_artifact(
                    project_id, artifact_id
                ):
                    for submission in recovery.submissions:
                        evidence_ids.extend(submission.evidence_ids_json)
        return list(dict.fromkeys(evidence_ids))

    async def _require_runnable_project(self, project_id: str) -> ProjectModel:
        project = await self._require_project(project_id)
        if project.status not in {
            ProjectStatus.RESEARCHING.value,
            ProjectStatus.SUPPLEMENTING_RESEARCH.value,
        }:
            raise AppError(
                code="TECHNICAL_FEASIBILITY_PROJECT_NOT_READY",
                message="项目必须先通过 Research Brief 审批。",
                status_code=409,
                details={"project_id": project_id, "status": project.status},
            )
        return project

    async def _require_project(self, project_id: str) -> ProjectModel:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
        if project is None:
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )
        return project

    @staticmethod
    def _public_runtime_error(error: RuntimeGatewayError) -> AppError:
        if error.code is RuntimeErrorCode.TIMEOUT:
            status_code, code = 504, "TECHNICAL_FEASIBILITY_TIMEOUT"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code, code = 409, "TECHNICAL_FEASIBILITY_CANCELLED"
        elif error.code is RuntimeErrorCode.PERMISSION_DENIED:
            status_code, code = 403, "TECHNICAL_FEASIBILITY_PERMISSION_DENIED"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code = 503, "TECHNICAL_FEASIBILITY_DEPENDENCY_UNAVAILABLE"
        else:
            status_code, code = 502, "TECHNICAL_FEASIBILITY_RUNTIME_FAILED"
        return AppError(
            code=code,
            message="技术可行性 Agent 未能生成通过证据门禁的评估。",
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
            },
        )
