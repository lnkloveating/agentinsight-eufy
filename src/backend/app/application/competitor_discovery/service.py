"""运行竞品候选 Agent，并在人工确认后原子更新正式竞品范围。"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.agents.competitor.discovery_contracts import (
    CompetitorCandidateDecision,
    CompetitorCandidateDecisionAction,
    CompetitorCandidateDecisionCreate,
    CompetitorCandidateDecisionResult,
    CompetitorDiscoveryArtifact,
    CompetitorDiscoveryCandidateReference,
    CompetitorDiscoveryInputContext,
    CompetitorDiscoveryPayload,
    CompetitorDiscoveryProposal,
    CompetitorDiscoveryRunCreate,
)
from app.application.events import ProjectEventBroker
from app.application.runtime import (
    AgentRuntimeGateway,
    ArtifactAccessDeniedError,
    ArtifactStore,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.application.source_requirements import SourceRequirementService
from app.core.errors import AppError
from app.infrastructure.database.competitor_discovery_repository import (
    CompetitorDiscoveryRepository,
)
from app.infrastructure.database.models import (
    CompetitorCandidateDecisionModel,
    ProjectEventModel,
    ProjectModel,
    SearchDiscoveryRunModel,
    SourceRequirementScopeModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.project import ProjectStatus, ResearchBrief
from app.schemas.search_discovery import (
    SearchDiscoveryCandidate,
    SearchDiscoveryIntent,
    SearchDiscoveryRunStatus,
)
from app.schemas.source_requirements import (
    CompetitorResearchDimension,
    ProductReference,
    SourceRequirementScopeUpdate,
)
from app.workflows.contracts import (
    AgentContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
    ResearchTaskStatus,
)

COMPETITOR_DISCOVERY_TASK_ID = "task_competitor_discovery"


class CompetitorDiscoveryService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        event_broker: ProjectEventBroker,
        trace_id: str,
        *,
        max_input_candidates: int = 50,
        max_snippet_chars: int = 1_000,
        deadline_seconds: int = 180,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.event_broker = event_broker
        self.trace_id = trace_id
        self.max_input_candidates = max_input_candidates
        self.max_snippet_chars = max_snippet_chars
        self.deadline_seconds = deadline_seconds
        self.artifact_store = ArtifactStore(database)
        self.requirement_service = SourceRequirementService(database, event_broker, trace_id)

    async def run(
        self, project_id: str, payload: CompetitorDiscoveryRunCreate
    ) -> CompetitorDiscoveryArtifact:
        project, discovery_context = await self._build_context(project_id, payload)
        previous = await self.artifact_store.list_versions(
            project_id, COMPETITOR_DISCOVERY_TASK_ID
        )
        task = ResearchTask(
            task_id=COMPETITOR_DISCOVERY_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
            goal=(
                "基于当前项目的搜索候选识别准确型号的直接竞品，并生成等待人工确认的"
                "候选名单。"
            ),
            scope={"discovery_context": discovery_context.model_dump(mode="json")},
            required_artifacts=["search_discovery_candidates"],
            evidence_rules=EvidenceRules(
                citation_required=False,
                minimum_independent_domains=1,
            ),
            budget=ResearchBudget(
                max_pages=len(discovery_context.candidates),
                max_iterations=1,
                deadline_seconds=self.deadline_seconds,
            ),
            acceptance_checks=[
                "每个提名必须有准确品牌、型号和输入 candidate_id",
                "每个输入 candidate_id 必须恰好被提名或排除一次",
                "搜索候选不得写入 evidence_ids 或改写成已验证事实",
                "人工 Candidate Gate 前不得更新正式竞品范围",
            ],
        )
        context = AgentContext(
            project_id=project_id,
            brief=ResearchBrief.model_validate(project.brief_json),
            iteration=len(previous),
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        stored = await self.artifact_store.get(project_id, artifact.artifact_id)
        if stored is None:
            raise AppError(
                code="COMPETITOR_DISCOVERY_ARTIFACT_NOT_FOUND",
                message="竞品候选 Artifact 保存失败。",
                status_code=500,
            )
        return CompetitorDiscoveryArtifact.from_stored(stored, decision=None)

    async def list_artifacts(self, project_id: str) -> list[CompetitorDiscoveryArtifact]:
        await self._require_project(project_id)
        stored_items = await self.artifact_store.list_versions(
            project_id, COMPETITOR_DISCOVERY_TASK_ID
        )
        artifact_ids = {item.artifact.artifact_id for item in stored_items}
        async with self.database.session() as session:
            decisions = await CompetitorDiscoveryRepository(session).get_decisions(
                project_id, artifact_ids
            )
        decisions_by_artifact = {
            item.artifact_id: self._decision_schema(item) for item in decisions
        }
        return [
            CompetitorDiscoveryArtifact.from_stored(
                stored,
                decision=decisions_by_artifact.get(stored.artifact.artifact_id),
            )
            for stored in stored_items
        ]

    async def decide(
        self,
        project_id: str,
        artifact_id: str,
        payload: CompetitorCandidateDecisionCreate,
    ) -> CompetitorCandidateDecisionResult:
        try:
            stored = await self.artifact_store.get(project_id, artifact_id)
        except ArtifactAccessDeniedError as exc:
            raise self._artifact_not_found(artifact_id) from exc
        if stored is None or stored.artifact.task_id != COMPETITOR_DISCOVERY_TASK_ID:
            raise self._artifact_not_found(artifact_id)
        artifact_payload = CompetitorDiscoveryPayload.model_validate(stored.artifact.payload)
        proposals_by_id = {item.proposal_id: item for item in artifact_payload.proposals}
        unsupported = sorted(set(payload.selected_proposal_ids) - set(proposals_by_id))
        if unsupported:
            raise AppError(
                code="COMPETITOR_CANDIDATE_SELECTION_INVALID",
                message="选择中包含当前 Artifact 不存在的 proposal_id。",
                status_code=422,
                details={"unsupported_proposal_ids": unsupported},
            )
        if (
            payload.action is CompetitorCandidateDecisionAction.CONFIRM
            and stored.artifact.status is ResearchTaskStatus.BLOCKED
        ):
            raise AppError(
                code="COMPETITOR_CANDIDATE_CONFIRM_BLOCKED",
                message="没有准确型号的候选，不能确认竞品范围。",
                status_code=409,
            )

        now = datetime.now(UTC)
        decision_model = CompetitorCandidateDecisionModel(
            decision_id=f"candidate_decision_{uuid4().hex[:12]}",
            project_id=project_id,
            artifact_id=artifact_id,
            action=payload.action,
            selected_proposal_ids_json=payload.selected_proposal_ids,
            actor=payload.actor,
            reason=payload.reason,
            created_at=now,
        )
        async with self.database.session() as session:
            repository = CompetitorDiscoveryRepository(session)
            if await repository.get_artifact(project_id, artifact_id) is None:
                raise self._artifact_not_found(artifact_id)
            if await repository.get_decision(project_id, artifact_id) is not None:
                raise AppError(
                    code="COMPETITOR_CANDIDATE_DECISION_EXISTS",
                    message="该竞品候选 Artifact 已经完成 Candidate Gate。",
                    status_code=409,
                    details={"artifact_id": artifact_id},
                )
            scope = await repository.get_scope(project_id)
            if scope is None:
                raise AppError(
                    code="SOURCE_REQUIREMENT_SCOPE_REQUIRED",
                    message="必须先确认目标产品范围，才能审批竞品候选。",
                    status_code=409,
                )
            if self._product_identities(scope.target_products_json) != self._product_identities(
                [item.model_dump(mode="json") for item in artifact_payload.target_products]
            ):
                raise AppError(
                    code="COMPETITOR_DISCOVERY_ARTIFACT_STALE",
                    message="目标产品范围已经变化，请重新运行竞品候选发现。",
                    status_code=409,
                )
            if payload.action is CompetitorCandidateDecisionAction.CONFIRM:
                self._merge_selected_scope(
                    scope,
                    [proposals_by_id[item] for item in payload.selected_proposal_ids],
                    payload,
                    now,
                )
            await repository.add_decision(decision_model)
            project_repository = ProjectRepository(session)
            await project_repository.add_event(
                self._event(
                    project_id,
                    "competitor_candidate_gate_decided",
                    {
                        "artifact_id": artifact_id,
                        "decision_id": decision_model.decision_id,
                        "action": payload.action,
                        "selected_proposal_ids": payload.selected_proposal_ids,
                        "actor": payload.actor,
                    },
                    now,
                )
            )
            if payload.action is CompetitorCandidateDecisionAction.CONFIRM:
                await project_repository.add_event(
                    self._event(
                        project_id,
                        "source_requirement_scope_updated",
                        {
                            "target_product_count": len(scope.target_products_json),
                            "competitor_count": len(scope.competitors_json),
                            "dimensions": scope.dimensions_json,
                            "actor": payload.actor,
                            "source": "competitor_candidate_gate",
                        },
                        now,
                    )
                )
            try:
                await repository.commit()
            except IntegrityError as exc:
                await repository.rollback()
                raise AppError(
                    code="COMPETITOR_CANDIDATE_DECISION_EXISTS",
                    message="该竞品候选 Artifact 已经完成 Candidate Gate。",
                    status_code=409,
                    details={"artifact_id": artifact_id},
                ) from exc
            except Exception:
                await repository.rollback()
                raise
        await self.event_broker.notify(project_id)
        decision = self._decision_schema(decision_model)
        return CompetitorCandidateDecisionResult(
            artifact=CompetitorDiscoveryArtifact.from_stored(stored, decision=decision),
            source_requirements=await self.requirement_service.get(project_id),
        )

    async def _build_context(
        self,
        project_id: str,
        payload: CompetitorDiscoveryRunCreate,
    ) -> tuple[ProjectModel, CompetitorDiscoveryInputContext]:
        async with self.database.session() as session:
            repository = CompetitorDiscoveryRepository(session)
            project = await repository.get_project(project_id)
            if project is None:
                raise self._project_not_found(project_id)
            if project.status not in {
                ProjectStatus.RESEARCHING.value,
                ProjectStatus.SUPPLEMENTING_RESEARCH.value,
            }:
                raise AppError(
                    code="COMPETITOR_DISCOVERY_PROJECT_NOT_READY",
                    message="项目必须先通过 Brief 审批才能运行竞品候选发现 Agent。",
                    status_code=409,
                    details={"project_id": project_id, "status": project.status},
                )
            scope = await repository.get_scope(project_id)
            if scope is None or not scope.target_products_json:
                raise AppError(
                    code="COMPETITOR_DISCOVERY_TARGET_SCOPE_REQUIRED",
                    message="必须先在资料范围中确认至少一个目标产品。",
                    status_code=409,
                )
            target_products = [
                ProductReference.model_validate(item) for item in scope.target_products_json
            ]
            if any(item.model is None for item in target_products):
                raise AppError(
                    code="COMPETITOR_DISCOVERY_TARGET_MODEL_REQUIRED",
                    message="目标产品必须包含准确型号，才能发现可比较竞品。",
                    status_code=409,
                )
            requested_ids = set(payload.search_discovery_run_ids)
            runs = await repository.get_search_runs(project_id, requested_ids)
        runs_by_id = {item.search_discovery_run_id: item for item in runs}
        found_ids = set(runs_by_id)
        missing = sorted(requested_ids - found_ids)
        if missing:
            raise AppError(
                code="SEARCH_DISCOVERY_RUN_NOT_FOUND",
                message="部分搜索发现运行不存在或不属于当前项目。",
                status_code=404,
                details={"search_discovery_run_ids": missing},
            )
        invalid_runs = {
            item.search_discovery_run_id: {
                "status": item.status,
                "intent": item.intent,
            }
            for item in runs
            if item.status != SearchDiscoveryRunStatus.SUCCEEDED.value
            or item.intent != SearchDiscoveryIntent.COMPETITOR_CANDIDATE.value
        }
        if invalid_runs:
            raise AppError(
                code="COMPETITOR_DISCOVERY_SEARCH_RUN_INVALID",
                message="竞品发现只能使用已成功的 competitor_candidate 搜索运行。",
                status_code=409,
                details={"invalid_runs": invalid_runs},
            )
        runs = [runs_by_id[run_id] for run_id in payload.search_discovery_run_ids]
        candidates = self._candidate_context(runs)
        if not candidates:
            raise AppError(
                code="COMPETITOR_DISCOVERY_CANDIDATES_REQUIRED",
                message="搜索运行没有可供竞品发现 Agent 使用的候选。",
                status_code=409,
            )
        if len(candidates) > self.max_input_candidates:
            raise AppError(
                code="COMPETITOR_DISCOVERY_CANDIDATE_LIMIT_EXCEEDED",
                message="搜索候选数量超过单次 Agent 的安全上限。",
                status_code=422,
                details={
                    "candidate_count": len(candidates),
                    "max_input_candidates": self.max_input_candidates,
                },
            )
        context_hash = self._context_hash(
            target_products,
            payload.search_discovery_run_ids,
            candidates,
            payload.minimum_candidates,
        )
        return project, CompetitorDiscoveryInputContext(
            target_products=target_products,
            search_discovery_run_ids=payload.search_discovery_run_ids,
            candidates=candidates,
            minimum_candidates=payload.minimum_candidates,
            context_hash=context_hash,
        )

    def _candidate_context(
        self, runs: list[SearchDiscoveryRunModel]
    ) -> list[CompetitorDiscoveryCandidateReference]:
        candidates: list[CompetitorDiscoveryCandidateReference] = []
        seen: set[str] = set()
        for run in runs:
            run_id = run.search_discovery_run_id
            for raw in run.candidates_json:
                candidate = SearchDiscoveryCandidate.model_validate(raw)
                if candidate.candidate_id in seen:
                    continue
                seen.add(candidate.candidate_id)
                candidates.append(
                    CompetitorDiscoveryCandidateReference.model_validate(
                        {
                            "candidate_id": candidate.candidate_id,
                            "search_discovery_run_id": run_id,
                            "title": candidate.title,
                            "source_url": candidate.normalized_source_url,
                            "source_domain": candidate.source_domain,
                            "snippet": candidate.snippet[: self.max_snippet_chars],
                            "search_score": candidate.score,
                        }
                    )
                )
        return candidates

    @staticmethod
    def _context_hash(
        target_products: list[ProductReference],
        run_ids: list[str],
        candidates: list[CompetitorDiscoveryCandidateReference],
        minimum_candidates: int,
    ) -> str:
        canonical = json.dumps(
            {
                "target_products": [item.model_dump(mode="json") for item in target_products],
                "search_discovery_run_ids": run_ids,
                "candidates": [item.model_dump(mode="json") for item in candidates],
                "minimum_candidates": minimum_candidates,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_selected_scope(
        scope: SourceRequirementScopeModel,
        proposals: list[CompetitorDiscoveryProposal],
        decision: CompetitorCandidateDecisionCreate,
        now: datetime,
    ) -> None:
        target_products = [
            ProductReference.model_validate(item) for item in scope.target_products_json
        ]
        competitors = [ProductReference.model_validate(item) for item in scope.competitors_json]
        identities = {
            CompetitorDiscoveryService._product_identity(item) for item in competitors
        }
        for proposal in proposals:
            product = ProductReference(
                brand=proposal.brand,
                model=proposal.model,
                variant=proposal.variant,
            )
            identity = CompetitorDiscoveryService._product_identity(product)
            if identity not in identities:
                identities.add(identity)
                competitors.append(product)
        try:
            validated = SourceRequirementScopeUpdate(
                target_products=target_products,
                competitors=competitors,
                dimensions=[CompetitorResearchDimension(item) for item in scope.dimensions_json],
                actor=decision.actor,
                reason=decision.reason,
            )
        except ValidationError as exc:
            raise AppError(
                code="COMPETITOR_CANDIDATE_SCOPE_CONFLICT",
                message="确认的竞品与当前产品范围冲突，请重新运行候选发现。",
                status_code=409,
                details={"validation_errors": exc.errors(include_url=False)},
            ) from exc
        scope.target_products_json = [
            item.model_dump(mode="json") for item in validated.target_products
        ]
        scope.competitors_json = [item.model_dump(mode="json") for item in validated.competitors]
        scope.dimensions_json = [item.value for item in validated.dimensions]
        scope.updated_by = decision.actor
        scope.update_reason = decision.reason
        scope.updated_at = now

    @staticmethod
    def _product_identities(items: list[dict[str, object]]) -> set[tuple[str, str, str]]:
        return {
            CompetitorDiscoveryService._product_identity(ProductReference.model_validate(item))
            for item in items
        }

    @staticmethod
    def _product_identity(product: ProductReference) -> tuple[str, str, str]:
        return (
            product.brand.casefold(),
            (product.model or "").casefold(),
            (product.variant or "").casefold(),
        )

    @staticmethod
    def _decision_schema(model: CompetitorCandidateDecisionModel) -> CompetitorCandidateDecision:
        return CompetitorCandidateDecision(
            decision_id=model.decision_id,
            project_id=model.project_id,
            artifact_id=model.artifact_id,
            action=CompetitorCandidateDecisionAction(model.action),
            selected_proposal_ids=model.selected_proposal_ids_json,
            actor=model.actor,
            reason=model.reason,
            created_at=model.created_at,
        )

    async def _require_project(self, project_id: str) -> ProjectModel:
        async with self.database.session() as session:
            project = await CompetitorDiscoveryRepository(session).get_project(project_id)
        if project is None:
            raise self._project_not_found(project_id)
        return project

    def _event(
        self,
        project_id: str,
        event_type: str,
        data: dict[str, object],
        created_at: datetime,
    ) -> ProjectEventModel:
        return ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type=event_type,
            data_json=data,
            trace_id=self.trace_id,
            created_at=created_at,
        )

    @staticmethod
    def _artifact_not_found(artifact_id: str) -> AppError:
        return AppError(
            code="COMPETITOR_DISCOVERY_ARTIFACT_NOT_FOUND",
            message="竞品候选 Artifact 不存在或不属于当前项目。",
            status_code=404,
            details={"artifact_id": artifact_id},
        )

    @staticmethod
    def _project_not_found(project_id: str) -> AppError:
        return AppError(
            code="PROJECT_NOT_FOUND",
            message="研究项目不存在。",
            status_code=404,
            details={"project_id": project_id},
        )

    @staticmethod
    def _public_runtime_error(error: RuntimeGatewayError) -> AppError:
        if error.code is RuntimeErrorCode.TIMEOUT:
            status_code, code, message = (
                504,
                "COMPETITOR_DISCOVERY_TIMEOUT",
                "竞品候选发现 Agent 执行超时。",
            )
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code, message = (
                503,
                "COMPETITOR_DISCOVERY_DEPENDENCY_UNAVAILABLE",
                "竞品候选发现 Agent 的模型或 Runtime 尚不可用。",
            )
        else:
            status_code, code, message = (
                502,
                "COMPETITOR_DISCOVERY_RUNTIME_FAILED",
                "竞品候选发现 Agent 未能生成通过校验的 Artifact。",
            )
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
