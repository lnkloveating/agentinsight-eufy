"""Application service for versioned dry-run Security Policy compilation."""

from app.agents.security_policy import (
    SecurityPolicyArtifact,
    SecurityPolicyContextBuilder,
    SecurityPolicyRunCreate,
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

SECURITY_POLICY_TASK_ID = "task_security_policy"


class SecurityPolicyService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: SecurityPolicyContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(
        self, project_id: str, request: SecurityPolicyRunCreate
    ) -> SecurityPolicyArtifact:
        project = await self._require_runnable_project(project_id)
        opportunity = await self.artifact_store.latest_by_type(
            project_id, ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value
        )
        technical = await self.artifact_store.latest_by_type(
            project_id, ResearchAgentType.TECHNICAL_FEASIBILITY.value
        )
        if opportunity is None or technical is None:
            raise AppError(
                code="SECURITY_POLICY_UPSTREAM_REQUIRED",
                message="必须先生成生态机会与技术可行性 Artifact，才能编译安全策略。",
                status_code=409,
            )
        research_artifacts = {}
        for agent_type in (
            ResearchAgentType.USER_RESEARCH,
            ResearchAgentType.COMPETITOR_RESEARCH,
        ):
            stored = await self.artifact_store.latest_by_type(project_id, agent_type.value)
            if stored is not None:
                research_artifacts[agent_type.value] = stored.artifact
        handoff = build_research_handoff(research_artifacts)
        previous = await self.artifact_store.list_versions(
            project_id, SECURITY_POLICY_TASK_ID
        )
        supplemental = await self._resolved_supplemental_evidence_ids(
            project_id, [item.artifact.artifact_id for item in previous]
        )
        evidence_context = await self.context_builder.build(
            project_id,
            handoff,
            opportunity.artifact,
            technical.artifact,
            supplemental,
        )
        task = ResearchTask(
            task_id=SECURITY_POLICY_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.SECURITY_POLICY,
            goal=(
                "把通过技术可行性验证的开放家庭安全目标转换为受限、可解释、可降级且只用于"
                "dry-run 的跨设备 Security Policy DSL。"
            ),
            scope={"selected_opportunity_ids": request.selected_opportunity_ids},
            required_artifacts=[
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
                ResearchAgentType.TECHNICAL_FEASIBILITY.value,
            ],
            evidence_rules=EvidenceRules(citation_required=True),
            budget=ResearchBudget(
                max_pages=evidence_context.included_evidence_count,
                max_iterations=2,
                deadline_seconds=180,
            ),
            depends_on=[technical.artifact.task_id],
            acceptance_checks=[
                "只引用授权信号与生态设备角色",
                "只使用 Research Brief 允许的干预",
                "高影响动作必须人工批准",
                "五类失败均有确定性 fallback",
                "execution_mode 固定为 dry_run",
            ],
        )
        upstream = {
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value: opportunity.artifact,
            ResearchAgentType.TECHNICAL_FEASIBILITY.value: technical.artifact,
        }
        if previous:
            upstream[ResearchAgentType.SECURITY_POLICY.value] = previous[-1].artifact
        context = AgentContext(
            project_id=project_id,
            brief=ResearchBrief.model_validate(project.brief_json),
            iteration=len(previous),
            upstream_artifacts=upstream,
            selected_innovation_ids=request.selected_opportunity_ids,
            evidence_context=evidence_context,
            research_handoff=handoff,
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return SecurityPolicyArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[SecurityPolicyArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(
            project_id, SECURITY_POLICY_TASK_ID
        )
        return [
            SecurityPolicyArtifact.from_research_artifact(item.artifact)
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
                code="SECURITY_POLICY_PROJECT_NOT_READY",
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
            status_code, code = 504, "SECURITY_POLICY_TIMEOUT"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code, code = 409, "SECURITY_POLICY_CANCELLED"
        elif error.code is RuntimeErrorCode.PERMISSION_DENIED:
            status_code, code = 403, "SECURITY_POLICY_PERMISSION_DENIED"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code = 503, "SECURITY_POLICY_DEPENDENCY_UNAVAILABLE"
        else:
            status_code, code = 502, "SECURITY_POLICY_RUNTIME_FAILED"
        return AppError(
            code=code,
            message="安全策略 Compiler 未能生成通过权限和安全校验的 dry-run DSL。",
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
                **error.details,
            },
        )
