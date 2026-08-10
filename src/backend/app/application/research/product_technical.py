"""Production use case for future product opportunity generation."""

from app.agents.product_technical import (
    ProductTechnicalArtifact,
    ProductTechnicalEvidenceContextBuilder,
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

PRODUCT_TECHNICAL_TASK_ID = "task_product_technical"


class ProductTechnicalService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: ProductTechnicalEvidenceContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(self, project_id: str) -> ProductTechnicalArtifact:
        project = await self._require_runnable_project(project_id)
        previous = await self.artifact_store.list_versions(project_id, PRODUCT_TECHNICAL_TASK_ID)
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
        evidence_context = (
            await self.context_builder.build(project_id, handoff)
            if handoff.ready_for_product_technical
            else None
        )
        task = ResearchTask(
            task_id=PRODUCT_TECHNICAL_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.PRODUCT_TECHNICAL,
            goal=(
                "把用户研究事件与竞品缺口交叉验证，动态生成未来产品机会；目标三个、最多五个，"
                "证据不足时输出更少候选和明确补研问题。"
            ),
            scope={
                "category": project.brief_json.get("category"),
                "target_user": project.brief_json.get("target_user"),
                "region": project.brief_json.get("region"),
            },
            required_artifacts=[
                ResearchAgentType.USER_RESEARCH.value,
                ResearchAgentType.COMPETITOR_RESEARCH.value,
            ],
            evidence_rules=EvidenceRules(citation_required=True, minimum_independent_domains=2),
            budget=ResearchBudget(
                max_pages=evidence_context.included_evidence_count if evidence_context else 0,
                max_iterations=2,
                deadline_seconds=180,
            ),
            depends_on=[artifact.task_id for artifact in upstream.values()],
            acceptance_checks=[
                "每个候选同时引用用户研究与竞品研究 Evidence",
                "每个候选通过确定性 Event Understanding Gate 后才可晋级",
                "目标三个且最多五个候选，证据不足时不使用模板凑数",
            ],
        )
        context = AgentContext(
            project_id=project_id,
            brief=ResearchBrief.model_validate(project.brief_json),
            iteration=len(previous),
            upstream_artifacts=upstream,
            evidence_context=evidence_context,
            research_handoff=handoff,
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return ProductTechnicalArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[ProductTechnicalArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(project_id, PRODUCT_TECHNICAL_TASK_ID)
        return [ProductTechnicalArtifact.from_research_artifact(item.artifact) for item in versions]

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
                code="PRODUCT_TECHNICAL_PROJECT_NOT_READY",
                message="项目必须先通过 Brief 审批，才能运行产品技术 Agent。",
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
            status_code, code = 504, "PRODUCT_TECHNICAL_TIMEOUT"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code, code = 409, "PRODUCT_TECHNICAL_CANCELLED"
        elif error.code is RuntimeErrorCode.PERMISSION_DENIED:
            status_code, code = 403, "PRODUCT_TECHNICAL_PERMISSION_DENIED"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code = 503, "PRODUCT_TECHNICAL_DEPENDENCY_UNAVAILABLE"
        else:
            status_code, code = 502, "PRODUCT_TECHNICAL_RUNTIME_FAILED"
        return AppError(
            code=code,
            message="产品技术 Agent 未能生成通过校验的机会组合。",
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
            },
        )
