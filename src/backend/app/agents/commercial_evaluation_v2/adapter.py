"""Internal model adapter for Commercial Evaluation v2."""

from __future__ import annotations

import json

from app.agents.commercial_evaluation_v2.context import (
    CommercialEvaluationContextBuilder,
)
from app.agents.commercial_evaluation_v2.contracts import (
    CommercialEvaluationModelOutput,
)
from app.agents.commercial_evaluation_v2.prompt import (
    COMMERCIAL_EVALUATION_PROMPT_KEY,
)
from app.agents.commercial_evaluation_v2.validation import (
    CommercialEvaluationOutputValidator,
    CommercialEvaluationValidationError,
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

_UPSTREAM_TYPES = (
    ResearchAgentType.USER_RESEARCH,
    ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
    ResearchAgentType.TECHNICAL_FEASIBILITY,
    ResearchAgentType.POLICY_VERIFICATION,
)


class CommercialEvaluationModelAgentAdapter:
    adapter_type = "commercial_evaluation_v2_internal_model"

    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        *,
        model_timeout_seconds: float = 180,
        validator: CommercialEvaluationOutputValidator | None = None,
        context_builder: CommercialEvaluationContextBuilder | None = None,
    ) -> None:
        if model_timeout_seconds <= 0:
            raise ValueError("model_timeout_seconds must be positive")
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.model_timeout_seconds = model_timeout_seconds
        self.validator = validator or CommercialEvaluationOutputValidator()
        self.context_builder = context_builder

    async def execute(self, invocation: AgentInvocation) -> object:
        invocation.cancellation_token.raise_if_cancelled()
        context = await self._prepare_context(invocation)
        missing = [
            item.value
            for item in _UPSTREAM_TYPES
            if item.value not in context.upstream_artifacts
        ]
        if missing:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "Commercial Evaluation v2 lacks required upstream Artifacts.",
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details={"missing_agent_types": missing},
            )
        upstream = {
            item: context.upstream_artifacts[item.value] for item in _UPSTREAM_TYPES
        }
        evidence_index = [
            {
                "evidence_id": item.evidence_id,
                "title": item.title,
                "claim_type": item.claim_type,
                "source_type": item.source_type,
                "source_domain": item.source_domain,
                "original_excerpt": item.original_excerpt,
            }
            for item in (context.evidence_context.items if context.evidence_context else [])
        ]
        try:
            model_id = await self.selection_resolver.resolve(
                invocation.task.project_id, ResearchAgentType.COMMERCIAL_EVALUATION
            )
            prompt = self.prompt_registry.resolve(COMMERCIAL_EVALUATION_PROMPT_KEY)
            rendered = prompt.render(
                {
                    "project_id": invocation.task.project_id,
                    "task_id": invocation.task.task_id,
                    "selected_opportunity_ids_json": json.dumps(
                        context.selected_innovation_ids, ensure_ascii=False
                    ),
                    "brief_json": context.brief.model_dump_json(),
                    "user_research_json": upstream[
                        ResearchAgentType.USER_RESEARCH
                    ].model_dump_json(),
                    "opportunity_json": upstream[
                        ResearchAgentType.ECOSYSTEM_OPPORTUNITY
                    ].model_dump_json(),
                    "technical_json": upstream[
                        ResearchAgentType.TECHNICAL_FEASIBILITY
                    ].model_dump_json(),
                    "verification_json": upstream[
                        ResearchAgentType.POLICY_VERIFICATION
                    ].model_dump_json(),
                    "evidence_index_json": json.dumps(
                        evidence_index, ensure_ascii=False, sort_keys=True
                    ),
                }
            )
        except (ModelSelectionResolutionError, PromptRegistryError) as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "Commercial Evaluation lacks model selection or Prompt configuration.",
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
                    response_model=CommercialEvaluationModelOutput,
                    timeout_seconds=min(
                        self.model_timeout_seconds,
                        float(invocation.task.budget.deadline_seconds),
                    ),
                    max_output_tokens=16_000,
                    provider_options={"temperature": 0.1, "thinking": {"type": "disabled"}},
                )
            )
        except ModelGatewayError as exc:
            raise self._runtime_error(invocation, exc) from exc
        try:
            return self.validator.validate(
                invocation.task,
                context,
                CommercialEvaluationModelOutput.model_validate(result.output),
            )
        except CommercialEvaluationValidationError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                str(exc),
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details=exc.details,
            ) from exc

    async def _prepare_context(self, invocation: AgentInvocation) -> AgentContext:
        context = invocation.context
        if context.evidence_context is not None:
            return context
        artifacts = [
            context.upstream_artifacts[item.value]
            for item in _UPSTREAM_TYPES
            if item.value in context.upstream_artifacts
        ]
        if self.context_builder is None or context.research_handoff is None:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "Commercial workflow lacks its bounded context builder.",
                agent_run_id=invocation.agent_run_id,
                retryable=False,
            )
        evidence = await self.context_builder.build(
            invocation.task.project_id,
            context.research_handoff,
            artifacts,
        )
        return context.model_copy(update={"evidence_context": evidence})

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
            "Commercial Evaluation model call failed.",
            agent_run_id=invocation.agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )
