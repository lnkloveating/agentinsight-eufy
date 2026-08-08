"""资料路由分析、模型审计、幂等保存与人工决策用例。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.application.events import ProjectEventBroker
from app.application.model_gateway import (
    ModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
    ModelResult,
    PromptDefinition,
    PromptRegistry,
    PromptRegistryError,
)
from app.application.model_gateway.selection import (
    ModelSelectionResolutionError,
    ProjectModelSelectionResolver,
)
from app.application.source_routing.prompt import SOURCE_ROUTING_PROMPT_KEY
from app.application.source_routing.rules import (
    DeterministicSourceRouter,
    SourceRoutingInput,
)
from app.core.errors import AppError
from app.infrastructure.database.models import (
    AgentRunModel,
    ProjectEventModel,
    ProjectModel,
    SourceAssetModel,
    SourceRoutingModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.runtime_repository import AgentRuntimeRepository
from app.infrastructure.database.session import Database
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.infrastructure.database.source_routing_repository import SourceRoutingRepository
from app.schemas.source import SourceAssetStatus
from app.schemas.source_routing import (
    SourceRouting,
    SourceRoutingAnalyze,
    SourceRoutingDecision,
    SourceRoutingDecisionAction,
    SourceRoutingMethod,
    SourceRoutingModelOutput,
    SourceRoutingStatus,
    SourceRoutingSuggestedBy,
    SourceRoutingSuggestion,
)


class SourceRoutingService:
    def __init__(
        self,
        database: Database,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        event_broker: ProjectEventBroker,
        trace_id: str,
        *,
        max_fragments: int = 40,
        max_excerpt_chars: int = 1_500,
        max_total_chars: int = 30_000,
        auto_confirm_threshold: float = 0.92,
        model_timeout_seconds: float = 120,
        router: DeterministicSourceRouter | None = None,
    ) -> None:
        if min(max_fragments, max_excerpt_chars, max_total_chars) <= 0:
            raise ValueError("source routing context limits must be positive")
        if not 0.5 <= auto_confirm_threshold <= 1:
            raise ValueError("source routing auto-confirm threshold is invalid")
        if model_timeout_seconds <= 0:
            raise ValueError("source routing model timeout must be positive")
        self.database = database
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.event_broker = event_broker
        self.trace_id = trace_id
        self.max_fragments = max_fragments
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars
        self.auto_confirm_threshold = auto_confirm_threshold
        self.model_timeout_seconds = model_timeout_seconds
        self.router = router or DeterministicSourceRouter()

    async def get(self, project_id: str, source_asset_id: str) -> SourceRouting:
        async with self.database.session() as session:
            source_repository = SourceAssetRepository(session)
            await self._require_source(source_repository, project_id, source_asset_id)
            model = await SourceRoutingRepository(session).get(project_id, source_asset_id)
        if model is None:
            raise AppError(
                code="SOURCE_ROUTING_NOT_FOUND",
                message="该资料尚未进行路由分析。",
                status_code=404,
                details={"source_asset_id": source_asset_id},
            )
        return self._to_schema(model)

    async def analyze(
        self,
        project_id: str,
        source_asset_id: str,
        payload: SourceRoutingAnalyze,
    ) -> SourceRouting:
        (
            source,
            brief_json,
            routing_input,
            rule_suggestions,
            rule_signals,
        ) = await self._load_analysis_input(project_id, source_asset_id)
        input_hash = routing_input.stable_hash()
        async with self.database.session() as session:
            existing = await SourceRoutingRepository(session).get(project_id, source_asset_id)
        if (
            existing is not None
            and existing.input_hash == input_hash
            and not payload.force
            and (
                not payload.use_model
                or existing.model_call_id is not None
                or existing.status == SourceRoutingStatus.CONFIRMED
            )
        ):
            return self._to_schema(existing)

        model_output: SourceRoutingModelOutput | None = None
        model_id: str | None = None
        model_call_id: str | None = None
        if payload.use_model and self._needs_model(rule_suggestions):
            try:
                model_output, model_id, model_call_id = await self._classify_with_model(
                    project_id,
                    source,
                    brief_json,
                    routing_input,
                    rule_suggestions,
                )
            except (ModelGatewayError, ModelSelectionResolutionError, PromptRegistryError) as exc:
                rule_signals = [
                    *rule_signals,
                    f"model_fallback:{getattr(exc, 'code', type(exc).__name__)}",
                ]

        suggestions = self._merge_suggestions(
            rule_suggestions,
            model_output.suggestions if model_output is not None else [],
        )
        auto_confirm = self._can_auto_confirm(suggestions)
        status = SourceRoutingStatus.CONFIRMED if auto_confirm else SourceRoutingStatus.NEEDS_REVIEW
        method = self._method(rule_suggestions, model_output)
        confirmed_routes = [item.route.value for item in suggestions] if auto_confirm else []
        confirmed_claim_types = self._claim_type_values(suggestions) if auto_confirm else []
        now = datetime.now(UTC)
        async with self.database.session() as session:
            repository = SourceRoutingRepository(session)
            model = await repository.get(project_id, source_asset_id)
            if model is None:
                model = SourceRoutingModel(
                    source_routing_id=f"routing_{uuid4().hex[:16]}",
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    status=status,
                    method=method,
                    suggestions_json=self._suggestion_json(suggestions),
                    confirmed_routes_json=confirmed_routes,
                    confirmed_claim_types_json=confirmed_claim_types,
                    rule_signals_json=sorted(set(rule_signals)),
                    input_hash=input_hash,
                    model_id=model_id,
                    model_call_id=model_call_id,
                    analyzed_at=now,
                    updated_at=now,
                )
                await repository.add(model)
            else:
                model.status = status
                model.method = method
                model.suggestions_json = self._suggestion_json(suggestions)
                model.confirmed_routes_json = confirmed_routes
                model.confirmed_claim_types_json = confirmed_claim_types
                model.rule_signals_json = sorted(set(rule_signals))
                model.input_hash = input_hash
                model.model_id = model_id
                model.model_call_id = model_call_id
                model.analyzed_at = now
                model.decided_at = None
                model.decided_by = None
                model.decision_reason = None
                model.updated_at = now
            projects = ProjectRepository(session)
            await projects.add_event(
                self._event(
                    project_id,
                    source_asset_id,
                    "source_routing_analyzed",
                    now,
                    {
                        "status": status,
                        "method": method,
                        "suggestion_count": len(suggestions),
                        "confirmed_routes": confirmed_routes,
                    },
                )
            )
            await repository.commit()
            result = self._to_schema(model)
        await self.event_broker.notify(project_id)
        return result

    async def decide(
        self,
        project_id: str,
        source_asset_id: str,
        payload: SourceRoutingDecision,
    ) -> SourceRouting:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            source_repository = SourceAssetRepository(session)
            await self._require_source(source_repository, project_id, source_asset_id)
            repository = SourceRoutingRepository(session)
            model = await repository.get(project_id, source_asset_id)
            if model is None:
                raise AppError(
                    code="SOURCE_ROUTING_NOT_FOUND",
                    message="请先运行资料路由分析，再提交审核决定。",
                    status_code=409,
                )
            if payload.action is SourceRoutingDecisionAction.CONFIRM:
                model.status = SourceRoutingStatus.CONFIRMED
                model.confirmed_routes_json = [item.route.value for item in payload.selections]
                model.confirmed_claim_types_json = sorted(
                    {
                        claim_type.value
                        for item in payload.selections
                        for claim_type in item.claim_types
                    }
                )
            else:
                model.status = SourceRoutingStatus.REJECTED
                model.confirmed_routes_json = []
                model.confirmed_claim_types_json = []
            model.method = SourceRoutingMethod.MANUAL
            model.decided_at = now
            model.decided_by = payload.actor
            model.decision_reason = payload.reason
            model.updated_at = now
            projects = ProjectRepository(session)
            await projects.add_event(
                self._event(
                    project_id,
                    source_asset_id,
                    "source_routing_decided",
                    now,
                    {
                        "status": model.status,
                        "confirmed_routes": model.confirmed_routes_json,
                        "actor": payload.actor,
                    },
                )
            )
            await repository.commit()
            result = self._to_schema(model)
        await self.event_broker.notify(project_id)
        return result

    async def _load_analysis_input(
        self, project_id: str, source_asset_id: str
    ) -> tuple[
        SourceAssetModel,
        dict[str, object],
        SourceRoutingInput,
        list[SourceRoutingSuggestion],
        list[str],
    ]:
        async with self.database.session() as session:
            source_repository = SourceAssetRepository(session)
            source = await self._require_source(source_repository, project_id, source_asset_id)
            project = await session.get(ProjectModel, project_id)
            fragments, _, total = await source_repository.list_fragments(
                project_id, source_asset_id, limit=self.max_fragments
            )
        if total == 0:
            raise AppError(
                code="SOURCE_ROUTING_REQUIRES_PROCESSED_SOURCE",
                message="资料必须先完成解析，才能进行自动路由。",
                status_code=409,
                details={"source_asset_id": source_asset_id},
            )
        excerpts: list[str] = []
        used_chars = 0
        fragment_hashes: list[str] = []
        for fragment in fragments:
            remaining = self.max_total_chars - used_chars
            if remaining <= 0:
                break
            excerpt = fragment.original_excerpt[: min(self.max_excerpt_chars, remaining)]
            if excerpt:
                excerpts.append(excerpt)
                fragment_hashes.append(fragment.excerpt_hash)
                used_chars += len(excerpt)
        routing_input = SourceRoutingInput(
            source_asset_id=source.source_asset_id,
            content_hash=source.content_hash,
            display_name=source.display_name,
            source_url=source.source_url,
            media_type=source.media_type,
            media_category=source.media_category,
            authorization_basis=source.authorization_basis,
            purpose=source.purpose,
            fragment_hashes=fragment_hashes,
            excerpts=excerpts,
        )
        deterministic = self.router.classify(routing_input)
        brief_json = dict(project.brief_json) if project is not None else {}
        return (
            source,
            brief_json,
            routing_input,
            deterministic.suggestions,
            deterministic.signals,
        )

    async def _classify_with_model(
        self,
        project_id: str,
        source: SourceAssetModel,
        brief_json: dict[str, object],
        routing_input: SourceRoutingInput,
        rule_suggestions: list[SourceRoutingSuggestion],
    ) -> tuple[SourceRoutingModelOutput, str, str]:
        model_id = await self.selection_resolver.resolve_for_key(project_id, "source_routing")
        prompt = self.prompt_registry.resolve(SOURCE_ROUTING_PROMPT_KEY)
        rendered = prompt.render(
            {
                "brief_json": json.dumps(brief_json, ensure_ascii=False, sort_keys=True),
                "source_metadata_json": json.dumps(
                    {
                        "source_asset_id": source.source_asset_id,
                        "display_name": source.display_name,
                        "source_url": source.source_url,
                        "media_type": source.media_type,
                        "media_category": source.media_category,
                        "authorization_basis": source.authorization_basis,
                        "purpose": source.purpose,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "rule_suggestions_json": json.dumps(
                    [item.model_dump(mode="json") for item in rule_suggestions],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "fragment_context_json": json.dumps(routing_input.excerpts, ensure_ascii=False),
            }
        )
        run = await self._start_model_run(project_id, source.source_asset_id, model_id, prompt)
        try:
            result = await self.model_gateway.generate(
                ModelRequest(
                    project_id=project_id,
                    agent_run_id=run.agent_run_id,
                    trace_id=self.trace_id,
                    model_id=model_id,
                    prompt_key=prompt.prompt_key,
                    prompt_version=prompt.version,
                    messages=(
                        ModelMessage(role="system", content=rendered.system),
                        ModelMessage(role="user", content=rendered.user),
                    ),
                    response_model=SourceRoutingModelOutput,
                    timeout_seconds=self.model_timeout_seconds,
                    max_output_tokens=3_000,
                    provider_options={
                        "temperature": 0,
                        "thinking": {"type": "disabled"},
                    },
                )
            )
        except ModelGatewayError as exc:
            await self._finish_model_run(run.agent_run_id, error=exc)
            raise
        await self._finish_model_run(run.agent_run_id, result=result)
        return (
            SourceRoutingModelOutput.model_validate(result.output),
            result.model_id,
            result.model_call_id,
        )

    async def _start_model_run(
        self,
        project_id: str,
        source_asset_id: str,
        model_id: str,
        prompt: PromptDefinition,
    ) -> AgentRunModel:
        now = datetime.now(UTC)
        task_id = f"source_routing:{source_asset_id}"
        async with self.database.session() as session:
            repository = AgentRuntimeRepository(session)
            attempt = await repository.next_attempt_number(project_id, task_id)
            run = AgentRunModel(
                agent_run_id=f"run_{uuid4().hex[:16]}",
                project_id=project_id,
                agent_type="source_routing",
                agent_name="资料路由分类器",
                task_id=task_id,
                adapter_type="source_routing_internal_model",
                attempt_number=attempt,
                trace_id=self.trace_id,
                timeout_seconds=self.model_timeout_seconds,
                input_artifact_ids_json=[],
                status="running",
                progress=10,
                quality_score=0,
                evidence_ids_json=[],
                unknowns_json=[],
                message="正在对授权资料进行多标签路由分类。",
                started_at=now,
                model_id=model_id,
                prompt_key=prompt.prompt_key,
                prompt_version=prompt.version,
            )
            await repository.add_run(run)
            await repository.commit()
        return run

    async def _finish_model_run(
        self,
        agent_run_id: str,
        *,
        result: ModelResult | None = None,
        error: ModelGatewayError | None = None,
    ) -> None:
        async with self.database.session() as session:
            repository = AgentRuntimeRepository(session)
            run = await repository.get_run(agent_run_id)
            if run is None:  # pragma: no cover - the run was created immediately before use
                return
            run.completed_at = datetime.now(UTC)
            if error is not None:
                run.status = "failed"
                run.progress = 100
                run.message = "资料路由模型分类失败，系统已回退到确定性建议。"
                run.error_code = error.code
                run.error_message = str(error)
            else:
                if result is None:
                    raise TypeError("source routing model result has invalid type")
                run.status = "completed"
                run.progress = 100
                run.quality_score = 100
                run.message = "资料路由模型分类完成。"
                run.model_id = result.model_id
                run.model_provider = result.provider
                run.input_tokens = result.usage.input_tokens
                run.output_tokens = result.usage.output_tokens
                run.estimated_cost_microusd = result.estimated_cost_microusd
            await repository.commit()

    async def _require_source(
        self,
        repository: SourceAssetRepository,
        project_id: str,
        source_asset_id: str,
    ) -> SourceAssetModel:
        if not await repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )
        source = await repository.get_by_project(project_id, source_asset_id)
        if source is None:
            raise AppError(
                code="SOURCE_ASSET_NOT_FOUND",
                message="资料资产不存在。",
                status_code=404,
                details={"source_asset_id": source_asset_id},
            )
        if source.status == SourceAssetStatus.DELETED:
            raise AppError(
                code="SOURCE_ASSET_DELETED",
                message="已删除的资料不能进行路由分析。",
                status_code=409,
            )
        return source

    def _needs_model(self, suggestions: list[SourceRoutingSuggestion]) -> bool:
        return not suggestions or any(
            item.confidence < self.auto_confirm_threshold for item in suggestions
        )

    def _can_auto_confirm(self, suggestions: list[SourceRoutingSuggestion]) -> bool:
        return bool(suggestions) and all(
            item.confidence >= self.auto_confirm_threshold
            and item.suggested_by
            in {SourceRoutingSuggestedBy.RULE, SourceRoutingSuggestedBy.HYBRID}
            for item in suggestions
        )

    @staticmethod
    def _merge_suggestions(
        rules: list[SourceRoutingSuggestion], models: list[SourceRoutingSuggestion]
    ) -> list[SourceRoutingSuggestion]:
        merged = {item.route: item for item in rules}
        for model in models:
            rule = merged.get(model.route)
            if rule is None:
                merged[model.route] = model
                continue
            confidence = 1 - (1 - rule.confidence) * (1 - model.confidence)
            merged[model.route] = SourceRoutingSuggestion(
                route=model.route,
                claim_types=sorted(set(rule.claim_types) | set(model.claim_types), key=str),
                confidence=round(min(confidence, 0.99), 4),
                reason=f"规则：{rule.reason}；模型：{model.reason}",
                signals=sorted(set(rule.signals) | set(model.signals)),
                suggested_by=SourceRoutingSuggestedBy.HYBRID,
            )
        return sorted(merged.values(), key=lambda item: (-item.confidence, item.route.value))

    @staticmethod
    def _method(
        rules: list[SourceRoutingSuggestion], model: SourceRoutingModelOutput | None
    ) -> SourceRoutingMethod:
        if model is not None and rules:
            return SourceRoutingMethod.HYBRID
        if model is not None:
            return SourceRoutingMethod.MODEL
        return SourceRoutingMethod.DETERMINISTIC

    @staticmethod
    def _claim_type_values(suggestions: list[SourceRoutingSuggestion]) -> list[str]:
        return sorted({claim.value for item in suggestions for claim in item.claim_types})

    @staticmethod
    def _suggestion_json(
        suggestions: list[SourceRoutingSuggestion],
    ) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in suggestions]

    @staticmethod
    def _to_schema(model: SourceRoutingModel) -> SourceRouting:
        return SourceRouting.model_validate(
            {
                "source_routing_id": model.source_routing_id,
                "project_id": model.project_id,
                "source_asset_id": model.source_asset_id,
                "status": model.status,
                "method": model.method,
                "suggestions": model.suggestions_json,
                "confirmed_routes": model.confirmed_routes_json,
                "confirmed_claim_types": model.confirmed_claim_types_json,
                "rule_signals": model.rule_signals_json,
                "input_hash": model.input_hash,
                "model_id": model.model_id,
                "model_call_id": model.model_call_id,
                "analyzed_at": model.analyzed_at,
                "decided_at": model.decided_at,
                "decided_by": model.decided_by,
                "decision_reason": model.decision_reason,
                "updated_at": model.updated_at,
            }
        )

    def _event(
        self,
        project_id: str,
        source_asset_id: str,
        event_type: str,
        now: datetime,
        data: dict[str, object],
    ) -> ProjectEventModel:
        return ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type=event_type,
            data_json={"source_asset_id": source_asset_id, **data},
            trace_id=self.trace_id,
            created_at=now,
        )
