"""Internal model adapter for the Ecosystem Opportunity Agent."""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.agents.ecosystem_opportunity.context import (
    DeviceCapabilityGraphContext,
    EcosystemOpportunityContextBuilder,
)
from app.agents.ecosystem_opportunity.contracts import EcosystemOpportunityModelOutput
from app.agents.ecosystem_opportunity.prompt import ECOSYSTEM_OPPORTUNITY_PROMPT_KEY
from app.agents.ecosystem_opportunity.validation import (
    EcosystemOpportunityOutputValidator,
    EcosystemOpportunityValidationError,
)
from app.application.model_gateway import (
    ModelErrorCode,
    ModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
    PromptRegistry,
    PromptRegistryError,
)
from app.application.model_gateway.selection import (
    ModelSelectionResolutionError,
    ProjectModelSelectionResolver,
)
from app.application.runtime import AgentInvocation, RuntimeErrorCode, RuntimeGatewayError
from app.workflows.contracts import AgentContext, ResearchAgentType


class EcosystemOpportunityModelAgentAdapter:
    adapter_type = "ecosystem_opportunity_internal_model"

    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        *,
        model_timeout_seconds: float = 180,
        validator: EcosystemOpportunityOutputValidator | None = None,
        context_builder: EcosystemOpportunityContextBuilder | None = None,
    ) -> None:
        if model_timeout_seconds <= 0:
            raise ValueError("model_timeout_seconds must be positive")
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.model_timeout_seconds = model_timeout_seconds
        self.validator = validator or EcosystemOpportunityOutputValidator()
        self.context_builder = context_builder

    async def execute(self, invocation: AgentInvocation) -> object:
        invocation.cancellation_token.raise_if_cancelled()
        context, graph = await self._prepare_context(invocation)
        handoff = context.research_handoff
        if handoff is None or not handoff.ready_for_ecosystem_opportunity:
            issues = handoff.issues if handoff is not None else ["missing_research_handoff"]
            return self.validator.build_blocked(invocation.task, context, graph, issues)
        user = context.upstream_artifacts.get(ResearchAgentType.USER_RESEARCH.value)
        competitor = context.upstream_artifacts.get(ResearchAgentType.COMPETITOR_RESEARCH.value)
        if user is None or competitor is None:
            return self.validator.build_blocked(
                invocation.task,
                context,
                graph,
                ["missing_upstream_user_or_competitor_artifact"],
            )
        evidence_index = []
        if context.evidence_context is not None:
            evidence_index = [
                {
                    "evidence_id": item.evidence_id,
                    "title": item.title,
                    "claim_type": item.claim_type,
                    "product": item.product,
                    "source_type": item.source_type,
                    "source_domain": item.source_domain,
                    "original_excerpt": item.original_excerpt,
                }
                for item in context.evidence_context.items
            ]
        try:
            model_id = await self.selection_resolver.resolve(
                invocation.task.project_id, ResearchAgentType.ECOSYSTEM_OPPORTUNITY
            )
            prompt = self.prompt_registry.resolve(ECOSYSTEM_OPPORTUNITY_PROMPT_KEY)
            rendered = prompt.render(
                {
                    "project_id": invocation.task.project_id,
                    "task_id": invocation.task.task_id,
                    "iteration": str(context.iteration),
                    "goal": invocation.task.goal,
                    "brief_json": context.brief.model_dump_json(),
                    "research_handoff_json": handoff.model_dump_json(),
                    "user_research_json": user.model_dump_json(),
                    "competitor_research_json": competitor.model_dump_json(),
                    "device_capability_graph_json": graph.model_dump_json(),
                    "evidence_index_json": json.dumps(
                        evidence_index, ensure_ascii=False, sort_keys=True
                    ),
                    "decision_history_json": json.dumps(
                        [
                            item.model_dump(mode="json")
                            for item in context.decision_history
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        except (ModelSelectionResolutionError, PromptRegistryError) as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "Ecosystem Opportunity Agent lacks model selection or Prompt configuration.",
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details={"configuration_error": getattr(exc, "code", type(exc).__name__)},
            ) from exc
        try:
            result = await self.model_gateway.generate(
                ModelRequest(
                    project_id=invocation.task.project_id,
                    agent_run_id=invocation.agent_run_id,
                    trace_id=invocation.trace_id,
                    model_id=model_id,
                    prompt_key=prompt.prompt_key,
                    prompt_version=prompt.version,
                    messages=(
                        ModelMessage(role="system", content=rendered.system),
                        ModelMessage(role="user", content=rendered.user),
                    ),
                    response_model=EcosystemOpportunityModelOutput,
                    timeout_seconds=min(
                        self.model_timeout_seconds,
                        float(invocation.task.budget.deadline_seconds),
                    ),
                    max_output_tokens=16_000,
                    provider_options={"temperature": 0.2, "thinking": {"type": "disabled"}},
                )
            )
        except ModelGatewayError as exc:
            raise self._runtime_error(invocation, exc) from exc
        invocation.cancellation_token.raise_if_cancelled()
        try:
            return self.validator.validate(
                invocation.task,
                context,
                graph,
                EcosystemOpportunityModelOutput.model_validate(result.output),
            )
        except EcosystemOpportunityValidationError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                str(exc),
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details=exc.details,
            ) from exc

    async def _prepare_context(
        self, invocation: AgentInvocation
    ) -> tuple[AgentContext, DeviceCapabilityGraphContext]:
        context = invocation.context
        raw_graph = invocation.task.scope.get("device_capability_graph")
        if raw_graph is None:
            if self.context_builder is None or context.research_handoff is None:
                raise RuntimeGatewayError(
                    RuntimeErrorCode.DEPENDENCY_MISSING,
                    "Ecosystem Opportunity workflow lacks a Device Capability Graph builder.",
                    agent_run_id=invocation.agent_run_id,
                    retryable=False,
                )
            bundle = await self.context_builder.build(
                invocation.task.project_id, context.research_handoff
            )
            return (
                context.model_copy(update={"evidence_context": bundle.evidence_context}),
                bundle.capability_graph,
            )
        try:
            return context, DeviceCapabilityGraphContext.model_validate(raw_graph)
        except ValidationError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                "Ecosystem Opportunity task lacks a valid Device Capability Graph projection.",
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details={"validation_errors": exc.errors(include_url=False)},
            ) from exc

    @staticmethod
    def _runtime_error(
        invocation: AgentInvocation, error: ModelGatewayError
    ) -> RuntimeGatewayError:
        if error.code is ModelErrorCode.TIMEOUT:
            code = RuntimeErrorCode.TIMEOUT
        elif error.code is ModelErrorCode.CANCELLED:
            code = RuntimeErrorCode.CANCELLED
        elif error.code in {
            ModelErrorCode.MODEL_NOT_FOUND,
            ModelErrorCode.MODEL_DISABLED,
            ModelErrorCode.CREDENTIAL_MISSING,
            ModelErrorCode.AUTHENTICATION_FAILED,
            ModelErrorCode.PROVIDER_NOT_BOUND,
            ModelErrorCode.CAPABILITY_MISSING,
        }:
            code = RuntimeErrorCode.DEPENDENCY_MISSING
        elif error.code is ModelErrorCode.STRUCTURED_OUTPUT_INVALID:
            code = RuntimeErrorCode.SCHEMA_INVALID
        else:
            code = RuntimeErrorCode.ADAPTER_FAILED
        return RuntimeGatewayError(
            code,
            "Ecosystem Opportunity model call failed.",
            agent_run_id=invocation.agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )
