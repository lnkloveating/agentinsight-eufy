"""用户研究 Agent 的生产运行用例。"""

from app.agents.user_research.context import UserResearchEvidenceContextBuilder
from app.agents.user_research.contracts import UserResearchArtifact
from app.application.runtime import (
    AgentRuntimeGateway,
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

USER_RESEARCH_TASK_ID = "task_user_research"


class UserResearchService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: UserResearchEvidenceContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(self, project_id: str) -> UserResearchArtifact:
        project = await self._require_runnable_project(project_id)
        brief = ResearchBrief.model_validate(project.brief_json)
        previous = await self.artifact_store.list_versions(project_id, USER_RESEARCH_TASK_ID)
        evidence_context = await self.context_builder.build(project_id)
        task = ResearchTask(
            task_id=USER_RESEARCH_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.USER_RESEARCH,
            goal=(
                "基于当前项目的有效 Evidence 识别用户事件链、痛点、当前解决方式、"
                "未满足需求、样本偏差与补研缺口。"
            ),
            scope={
                "research_scope": brief.research_scope.value,
                "safety_domains": [item.value for item in brief.safety_domains],
                "target_ecosystems": brief.target_ecosystems,
                "target_users": brief.target_users,
                "markets": brief.markets,
                "safety_goals": brief.safety_goals,
                "risk_scenarios": brief.risk_scenarios,
            },
            required_artifacts=["evidence_context"],
            evidence_rules=EvidenceRules(
                citation_required=True,
                minimum_independent_domains=2,
            ),
            budget=ResearchBudget(
                max_pages=evidence_context.included_evidence_count,
                max_iterations=2,
                deadline_seconds=180,
            ),
            acceptance_checks=[
                "每个痛点和未满足需求至少引用一条 user_opinion Evidence",
                "所有引用属于当前项目并通过 Evidence 状态门禁",
                "证据不足时返回 partial 或 blocked，不补造结论",
            ],
        )
        context = AgentContext(
            project_id=project_id,
            brief=brief,
            iteration=len(previous),
            evidence_context=evidence_context,
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return UserResearchArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[UserResearchArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(project_id, USER_RESEARCH_TASK_ID)
        return [UserResearchArtifact.from_research_artifact(item.artifact) for item in versions]

    async def _require_runnable_project(self, project_id: str) -> ProjectModel:
        project = await self._require_project(project_id)
        allowed = {
            ProjectStatus.RESEARCHING.value,
            ProjectStatus.SUPPLEMENTING_RESEARCH.value,
        }
        if project.status not in allowed:
            raise AppError(
                code="USER_RESEARCH_PROJECT_NOT_READY",
                message="项目必须先通过 Brief 审批才能运行用户研究 Agent。",
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
            status_code = 504
            code = "USER_RESEARCH_TIMEOUT"
            message = "用户研究 Agent 执行超时，请缩小证据范围后重试。"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code = 409
            code = "USER_RESEARCH_CANCELLED"
            message = "用户研究 Agent 已取消。"
        elif error.code is RuntimeErrorCode.PERMISSION_DENIED:
            status_code = 403
            code = "USER_RESEARCH_PERMISSION_DENIED"
            message = "用户研究 Agent 无权使用当前资源。"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code = 503
            code = "USER_RESEARCH_DEPENDENCY_UNAVAILABLE"
            message = "用户研究 Agent 的模型或 Runtime 尚不可用。"
        else:
            status_code = 502
            code = "USER_RESEARCH_RUNTIME_FAILED"
            message = "用户研究 Agent 未能生成通过校验的研究产物。"
        return AppError(
            code=code,
            message=message,
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
            },
        )
