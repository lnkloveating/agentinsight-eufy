"""Application service for deterministic Security Policy dry-run verification."""

from app.agents.policy_verification import (
    PolicyVerificationArtifact,
    PolicyVerificationRunCreate,
)
from app.application.runtime import (
    AgentRuntimeGateway,
    ArtifactAccessDeniedError,
    ArtifactStore,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.core.errors import AppError
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.session import Database
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)

POLICY_VERIFICATION_TASK_ID = "task_policy_verification"


class PolicyVerificationService:
    def __init__(self, database: Database, runtime: AgentRuntimeGateway) -> None:
        self.database = database
        self.runtime = runtime
        self.artifact_store = ArtifactStore(database)

    async def run(
        self, project_id: str, request: PolicyVerificationRunCreate
    ) -> PolicyVerificationArtifact:
        project = await self._require_runnable_project(project_id)
        try:
            stored = (
                await self.artifact_store.get(project_id, request.policy_artifact_id)
                if request.policy_artifact_id is not None
                else await self.artifact_store.latest_by_type(
                    project_id, ResearchAgentType.SECURITY_POLICY.value
                )
            )
        except ArtifactAccessDeniedError as exc:
            raise AppError(
                code="POLICY_ARTIFACT_ACCESS_DENIED",
                message="指定的策略不属于当前项目。",
                status_code=403,
            ) from exc
        if stored is None or stored.artifact.artifact_type != ResearchAgentType.SECURITY_POLICY:
            raise AppError(
                code="SECURITY_POLICY_REQUIRED",
                message="必须先生成当前项目的 Security Policy Artifact。",
                status_code=409,
            )
        previous = await self.artifact_store.list_versions(
            project_id, POLICY_VERIFICATION_TASK_ID
        )
        task = ResearchTask(
            task_id=POLICY_VERIFICATION_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.POLICY_VERIFICATION,
            goal="在不控制真实设备的前提下验证 Security Policy 的规则与失败降级。",
            scope=request.model_dump(mode="json"),
            required_artifacts=[ResearchAgentType.SECURITY_POLICY.value],
            evidence_rules=EvidenceRules(citation_required=True),
            budget=ResearchBudget(max_pages=0, max_iterations=1, deadline_seconds=60),
            depends_on=[stored.artifact.task_id],
            acceptance_checks=[
                "dry_run_only",
                "all_fallback_types_covered",
                "user_scenarios_policy_bounded",
                "deterministic_assertions",
            ],
        )
        context = AgentContext(
            project_id=project_id,
            brief=ResearchBrief.model_validate(project.brief_json),
            iteration=len(previous),
            upstream_artifacts={ResearchAgentType.SECURITY_POLICY.value: stored.artifact},
            selected_innovation_ids=stored.artifact.payload.get(
                "selected_opportunity_ids", []
            ),
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return PolicyVerificationArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[PolicyVerificationArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(
            project_id, POLICY_VERIFICATION_TASK_ID
        )
        return [
            PolicyVerificationArtifact.from_research_artifact(item.artifact)
            for item in versions
        ]

    async def _require_runnable_project(self, project_id: str) -> ProjectModel:
        project = await self._require_project(project_id)
        if project.status not in {
            ProjectStatus.RESEARCHING.value,
            ProjectStatus.SUPPLEMENTING_RESEARCH.value,
        }:
            raise AppError(
                code="POLICY_VERIFICATION_PROJECT_NOT_READY",
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
        if error.code is RuntimeErrorCode.CANCELLED:
            status_code, code = 409, "POLICY_VERIFICATION_CANCELLED"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code = 503, "POLICY_VERIFICATION_DEPENDENCY_UNAVAILABLE"
        elif error.code in {
            RuntimeErrorCode.ARTIFACT_INVALID,
            RuntimeErrorCode.SCHEMA_INVALID,
        }:
            status_code, code = 422, "POLICY_VERIFICATION_INPUT_INVALID"
        else:
            status_code, code = 502, "POLICY_VERIFICATION_FAILED"
        return AppError(
            code=code,
            message="安全策略未能完成 dry-run 验证。",
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
                **error.details,
            },
        )
