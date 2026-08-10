"""Production use case for evidence-bounded ecosystem opportunity generation."""

from app.agents.ecosystem_opportunity import EcosystemOpportunityArtifact
from app.agents.ecosystem_opportunity.context import EcosystemOpportunityContextBuilder
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

ECOSYSTEM_OPPORTUNITY_TASK_ID = "task_ecosystem_opportunity"


class EcosystemOpportunityService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: EcosystemOpportunityContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(self, project_id: str) -> EcosystemOpportunityArtifact:
        project = await self._require_runnable_project(project_id)
        brief = ResearchBrief.model_validate(project.brief_json)
        previous = await self.artifact_store.list_versions(
            project_id, ECOSYSTEM_OPPORTUNITY_TASK_ID
        )
        upstream = {}
        for agent_type in (ResearchAgentType.USER_RESEARCH, ResearchAgentType.COMPETITOR_RESEARCH):
            stored = await self.artifact_store.latest_by_type(project_id, agent_type.value)
            if stored is not None:
                upstream[agent_type.value] = stored.artifact
        handoff = build_research_handoff(upstream)
        supplemental_evidence_ids = await self._resolved_supplemental_evidence_ids(
            project_id,
            [item.artifact.artifact_id for item in previous],
        )
        if supplemental_evidence_ids:
            handoff = handoff.model_copy(
                update={"supplemental_evidence_ids": supplemental_evidence_ids}
            )
        bundle = await self.context_builder.build(project_id, handoff)
        task = ResearchTask(
            task_id=ECOSYSTEM_OPPORTUNITY_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
            goal=(
                "把用户安全事件、竞品生态缺口和已证实的设备能力交叉验证，动态生成目标三个、"
                "最多五个可继续验证的 AI 原生家庭安防生态机会；证据不足时少生成并提出补研问题。"
            ),
            scope={
                "research_scope": brief.research_scope.value,
                "safety_domains": [item.value for item in brief.safety_domains],
                "target_ecosystems": brief.target_ecosystems,
                "comparison_ecosystems": brief.comparison_ecosystems,
                "target_users": brief.target_users,
                "markets": brief.markets,
                "safety_goals": brief.safety_goals,
                "risk_scenarios": brief.risk_scenarios,
                "device_capability_graph": bundle.capability_graph.model_dump(mode="json"),
            },
            required_artifacts=[
                ResearchAgentType.USER_RESEARCH.value,
                ResearchAgentType.COMPETITOR_RESEARCH.value,
                "device_capability_graph",
            ],
            evidence_rules=EvidenceRules(citation_required=True, minimum_independent_domains=2),
            budget=ResearchBudget(
                max_pages=bundle.evidence_context.included_evidence_count,
                max_iterations=2,
                deadline_seconds=180,
            ),
            depends_on=[artifact.task_id for artifact in upstream.values()],
            acceptance_checks=[
                "每个候选同时引用用户研究与竞品生态 Evidence",
                "现有设备能力只引用 Device Capability Graph 中可用的 Evidence",
                "未知能力保持技术假设并生成补研缺口",
                "候选动态生成且不得用固定场景模板凑数",
            ],
        )
        context = AgentContext(
            project_id=project_id,
            brief=brief,
            iteration=len(previous),
            upstream_artifacts=upstream,
            evidence_context=bundle.evidence_context,
            research_handoff=handoff,
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return EcosystemOpportunityArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[EcosystemOpportunityArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(
            project_id, ECOSYSTEM_OPPORTUNITY_TASK_ID
        )
        return [
            EcosystemOpportunityArtifact.from_research_artifact(item.artifact)
            for item in versions
        ]

    async def _resolved_supplemental_evidence_ids(
        self,
        project_id: str,
        artifact_ids: list[str],
    ) -> list[str]:
        evidence_ids: list[str] = []
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            for artifact_id in artifact_ids:
                recoveries = await repository.list_resolved_for_artifact(
                    project_id, artifact_id
                )
                for recovery in recoveries:
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
                code="ECOSYSTEM_OPPORTUNITY_PROJECT_NOT_READY",
                message="项目必须先通过 Research Brief 审批，才能运行生态机会 Agent。",
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
            status_code, code = 504, "ECOSYSTEM_OPPORTUNITY_TIMEOUT"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code, code = 409, "ECOSYSTEM_OPPORTUNITY_CANCELLED"
        elif error.code is RuntimeErrorCode.PERMISSION_DENIED:
            status_code, code = 403, "ECOSYSTEM_OPPORTUNITY_PERMISSION_DENIED"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code = 503, "ECOSYSTEM_OPPORTUNITY_DEPENDENCY_UNAVAILABLE"
        else:
            status_code, code = 502, "ECOSYSTEM_OPPORTUNITY_RUNTIME_FAILED"
        return AppError(
            code=code,
            message="生态机会 Agent 未能生成通过证据门禁的机会组合。",
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
            },
        )
