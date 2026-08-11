"""Application service for evidence-bound ecosystem Commercial Evaluation v2."""

from app.agents.commercial_evaluation_v2 import (
    CommercialEvaluationArtifact,
    CommercialEvaluationContextBuilder,
    CommercialEvaluationRunCreate,
)
from app.agents.policy_verification import (
    PolicyVerificationArtifact,
    VerificationStatus,
)
from app.agents.technical_feasibility import TechnicalFeasibilityArtifact
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

COMMERCIAL_EVALUATION_V2_TASK_ID = "task_commercial_evaluation_v2"
_REQUIRED_UPSTREAM = (
    ResearchAgentType.USER_RESEARCH,
    ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
    ResearchAgentType.TECHNICAL_FEASIBILITY,
    ResearchAgentType.POLICY_VERIFICATION,
)


class CommercialEvaluationV2Service:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: CommercialEvaluationContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(
        self, project_id: str, request: CommercialEvaluationRunCreate
    ) -> CommercialEvaluationArtifact:
        project = await self._require_runnable_project(project_id)
        stored = {
            item: await self.artifact_store.latest_by_type(project_id, item.value)
            for item in _REQUIRED_UPSTREAM
        }
        missing = [item.value for item, artifact in stored.items() if artifact is None]
        if missing:
            raise AppError(
                code="COMMERCIAL_EVALUATION_UPSTREAM_REQUIRED",
                message="必须先完成用户研究、生态机会、技术可行性和策略验证。",
                status_code=409,
                details={"missing_agent_types": missing},
            )
        artifacts = {item: value.artifact for item, value in stored.items() if value}
        technical = TechnicalFeasibilityArtifact.from_research_artifact(
            artifacts[ResearchAgentType.TECHNICAL_FEASIBILITY]
        )
        verification = PolicyVerificationArtifact.from_research_artifact(
            artifacts[ResearchAgentType.POLICY_VERIFICATION]
        )
        selected = request.opportunity_ids or technical.payload.selected_opportunity_ids
        if not selected:
            raise AppError(
                code="COMMERCIAL_EVALUATION_SCOPE_REQUIRED",
                message="没有可评估的已选生态机会。",
                status_code=409,
            )
        outside_technical_scope = sorted(
            set(selected) - set(technical.payload.selected_opportunity_ids)
        )
        if outside_technical_scope:
            raise AppError(
                code="COMMERCIAL_EVALUATION_SCOPE_INVALID",
                message="商业评估只能使用已完成技术可行性评估的生态机会。",
                status_code=422,
                details={"outside_technical_scope": outside_technical_scope},
            )
        if verification.payload.verification_status in {
            VerificationStatus.FAILED,
            VerificationStatus.INCONCLUSIVE,
        }:
            raise AppError(
                code="COMMERCIAL_EVALUATION_POLICY_NOT_READY",
                message="安全策略验证失败或无法得出结论，不能进入商业评估。",
                status_code=409,
                details={
                    "verification_status": (
                        verification.payload.verification_status.value
                    )
                },
            )
        research_artifacts = {
            item.value: artifacts[item]
            for item in (
                ResearchAgentType.USER_RESEARCH,
                ResearchAgentType.COMPETITOR_RESEARCH,
            )
            if item in artifacts
        }
        competitor = await self.artifact_store.latest_by_type(
            project_id, ResearchAgentType.COMPETITOR_RESEARCH.value
        )
        if competitor is not None:
            research_artifacts[ResearchAgentType.COMPETITOR_RESEARCH.value] = (
                competitor.artifact
            )
        handoff = build_research_handoff(research_artifacts)
        previous = await self.artifact_store.list_versions(
            project_id, COMMERCIAL_EVALUATION_V2_TASK_ID
        )
        supplemental = await self._resolved_supplemental_evidence_ids(
            project_id, [item.artifact.artifact_id for item in previous]
        )
        evidence_context = await self.context_builder.build(
            project_id,
            handoff,
            list(artifacts.values()),
            supplemental,
        )
        task = ResearchTask(
            task_id=COMMERCIAL_EVALUATION_V2_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.COMMERCIAL_EVALUATION,
            goal="判断 AI 原生家庭安防生态机会是否值得进入下一轮商业与用户试点验证。",
            scope={"opportunity_ids": selected},
            required_artifacts=[item.value for item in _REQUIRED_UPSTREAM],
            evidence_rules=EvidenceRules(citation_required=True),
            budget=ResearchBudget(
                max_pages=evidence_context.included_evidence_count,
                max_iterations=2,
                deadline_seconds=180,
            ),
            depends_on=[verification.task_id],
            acceptance_checks=[
                "user_value_uses_user_research_evidence",
                "business_claims_use_commercial_evidence",
                "delivery_consumes_upstream_verdicts",
                "no_weighted_score",
                "no_launch_or_profit_guarantee",
            ],
        )
        context = AgentContext(
            project_id=project_id,
            brief=ResearchBrief.model_validate(project.brief_json),
            iteration=len(previous),
            upstream_artifacts={item.value: artifact for item, artifact in artifacts.items()},
            selected_innovation_ids=selected,
            evidence_context=evidence_context,
            research_handoff=handoff,
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return CommercialEvaluationArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[CommercialEvaluationArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(
            project_id, COMMERCIAL_EVALUATION_V2_TASK_ID
        )
        return [
            CommercialEvaluationArtifact.from_research_artifact(item.artifact)
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
                code="COMMERCIAL_EVALUATION_PROJECT_NOT_READY",
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
            status_code, code = 504, "COMMERCIAL_EVALUATION_TIMEOUT"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code, code = 409, "COMMERCIAL_EVALUATION_CANCELLED"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code = 503, "COMMERCIAL_EVALUATION_DEPENDENCY_UNAVAILABLE"
        elif error.code in {
            RuntimeErrorCode.ARTIFACT_INVALID,
            RuntimeErrorCode.SCHEMA_INVALID,
        }:
            status_code, code = 422, "COMMERCIAL_EVALUATION_OUTPUT_INVALID"
        else:
            status_code, code = 502, "COMMERCIAL_EVALUATION_FAILED"
        return AppError(
            code=code,
            message="商业评估未能生成通过证据边界校验的结论。",
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
                **error.details,
            },
        )
