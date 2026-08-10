"""Production use case for competitor ecosystem analysis."""

from app.agents.competitor.ecosystem_context import (
    CompetitorEcosystemEvidenceContextBuilder,
)
from app.agents.competitor.ecosystem_contracts import CompetitorEcosystemArtifact
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

COMPETITOR_ECOSYSTEM_TASK_ID = "task_competitor_ecosystem"


class CompetitorEcosystemAnalysisService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: CompetitorEcosystemEvidenceContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(self, project_id: str) -> CompetitorEcosystemArtifact:
        project = await self._require_runnable_project(project_id)
        brief = ResearchBrief.model_validate(project.brief_json)
        previous = await self.artifact_store.list_versions(
            project_id, COMPETITOR_ECOSYSTEM_TASK_ID
        )
        evidence_context = await self.context_builder.build(project_id)
        products = list(
            dict.fromkeys(
                item.product for item in evidence_context.items if item.product is not None
            )
        )
        task = ResearchTask(
            task_id=COMPETITOR_ECOSYSTEM_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
            goal=(
                "基于确认的竞品范围和三类事实专家 Evidence，比较目标与对照家庭安防生态的"
                "跨设备协作、持续状态、主动补证、隐私、离线降级和商业边界。"
            ),
            scope={
                "research_scope": brief.research_scope.value,
                "target_ecosystems": brief.target_ecosystems,
                "comparison_ecosystems": brief.comparison_ecosystems,
                "product_scope": products,
                "markets": brief.markets,
                "safety_goals": brief.safety_goals,
                "risk_scenarios": brief.risk_scenarios,
            },
            required_artifacts=["competitor_discovery", "evidence_context"],
            evidence_rules=EvidenceRules(
                citation_required=True,
                minimum_independent_domains=2,
            ),
            budget=ResearchBudget(
                max_pages=evidence_context.included_evidence_count,
                max_iterations=2,
                deadline_seconds=600,
            ),
            acceptance_checks=[
                "每个非 unknown 生态能力判断引用当前项目 Evidence",
                "未覆盖资料保持 unknown，不改写成竞品没有",
                "具体产品事实与生态层推断保持分层",
                "机会信号仅作为下游 Ecosystem Opportunity Agent 待验证假设",
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
        versions = await self.artifact_store.list_versions(
            project_id, COMPETITOR_ECOSYSTEM_TASK_ID
        )
        stored = next(
            (
                item
                for item in reversed(versions)
                if item.artifact.artifact_id == artifact.artifact_id
            ),
            None,
        )
        if stored is None:
            raise AppError(
                code="COMPETITOR_ECOSYSTEM_ARTIFACT_NOT_PERSISTED",
                message="竞品生态分析已结束，但版本化 Artifact 无法读取。",
                status_code=500,
                details={"project_id": project_id, "artifact_id": artifact.artifact_id},
            )
        return CompetitorEcosystemArtifact.from_stored(stored)

    async def list_artifacts(self, project_id: str) -> list[CompetitorEcosystemArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(
            project_id, COMPETITOR_ECOSYSTEM_TASK_ID
        )
        return [CompetitorEcosystemArtifact.from_stored(item) for item in versions]

    async def _require_runnable_project(self, project_id: str) -> ProjectModel:
        project = await self._require_project(project_id)
        if project.status not in {
            ProjectStatus.RESEARCHING.value,
            ProjectStatus.SUPPLEMENTING_RESEARCH.value,
        }:
            raise AppError(
                code="COMPETITOR_ECOSYSTEM_PROJECT_NOT_READY",
                message="项目必须先通过 Brief 审批才能运行竞品生态分析。",
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
            code = "COMPETITOR_ECOSYSTEM_TIMEOUT"
            message = "竞品生态分析超时，请缩小证据范围后重试。"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code = 409
            code = "COMPETITOR_ECOSYSTEM_CANCELLED"
            message = "竞品生态分析已取消。"
        elif error.code is RuntimeErrorCode.PERMISSION_DENIED:
            status_code = 403
            code = "COMPETITOR_ECOSYSTEM_PERMISSION_DENIED"
            message = "竞品生态分析无权使用当前资源。"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code = 503
            code = "COMPETITOR_ECOSYSTEM_DEPENDENCY_UNAVAILABLE"
            message = "竞品生态分析的模型或 Runtime 尚不可用。"
        else:
            status_code = 502
            code = "COMPETITOR_ECOSYSTEM_RUNTIME_FAILED"
            message = "竞品生态分析未能生成通过证据审计的产物。"
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
