"""Model adapter for evidence-bounded competitor synthesis."""

from __future__ import annotations

import json

from app.agents.competitor.synthesis_contracts import CompetitorSynthesisModelOutput
from app.agents.competitor.synthesis_prompt import COMPETITOR_SYNTHESIS_PROMPT_KEY
from app.agents.competitor.synthesis_validation import (
    CompetitorSynthesisOutputValidator,
    CompetitorSynthesisValidationError,
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
from app.integrations.a2a import CompetitorSpecialistArtifact, SpecialistTaskResult
from app.workflows.contracts import ResearchAgentType, ResearchArtifact


class CompetitorSynthesisModelAdapter:
    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        *,
        model_timeout_seconds: float = 180,
        validator: CompetitorSynthesisOutputValidator | None = None,
    ) -> None:
        if model_timeout_seconds <= 0:
            raise ValueError("model_timeout_seconds must be positive")
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.model_timeout_seconds = model_timeout_seconds
        self.validator = validator or CompetitorSynthesisOutputValidator()

    async def synthesize(
        self,
        invocation: AgentInvocation,
        results: list[SpecialistTaskResult],
    ) -> ResearchArtifact:
        invocation.cancellation_token.raise_if_cancelled()
        evidence_context = invocation.context.evidence_context
        if evidence_context is None:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                "Competitor synthesis requires the parent Evidence Context.",
                agent_run_id=invocation.agent_run_id,
                retryable=False,
            )
        artifacts = [result.artifact for result in results if result.artifact is not None]
        product_scope = list(dict.fromkeys(results[0].request.product_scope)) if results else []
        try:
            model_id = await self.selection_resolver.resolve(
                invocation.task.project_id, ResearchAgentType.COMPETITOR_RESEARCH
            )
            prompt = self.prompt_registry.resolve(COMPETITOR_SYNTHESIS_PROMPT_KEY)
            rendered = prompt.render(
                {
                    "project_id": invocation.task.project_id,
                    "task_id": invocation.task.task_id,
                    "brief_json": invocation.context.brief.model_dump_json(),
                    "product_scope_json": json.dumps(product_scope, ensure_ascii=False),
                    "specialist_outputs_json": json.dumps(
                        [artifact.model_dump(mode="json") for artifact in artifacts],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "evidence_index_json": json.dumps(
                        [
                            {
                                "evidence_id": item.evidence_id,
                                "product": item.product,
                                "claim_type": item.claim_type,
                                "source_type": item.source_type,
                                "source_domain": item.source_domain,
                            }
                            for item in evidence_context.items
                            if item.evidence_id
                            in {eid for artifact in artifacts for eid in artifact.evidence_ids}
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        except (ModelSelectionResolutionError, PromptRegistryError) as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "Competitor synthesis lacks model selection or prompt configuration.",
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
                    response_model=CompetitorSynthesisModelOutput,
                    timeout_seconds=self.model_timeout_seconds,
                    max_output_tokens=10_000,
                    provider_options={"temperature": 0.1, "thinking": {"type": "disabled"}},
                )
            )
        except ModelGatewayError as exc:
            raise self._runtime_error(invocation, exc) from exc
        invocation.cancellation_token.raise_if_cancelled()
        try:
            return self.validator.validate(
                artifact_id=f"artifact_pending_{invocation.agent_run_id}",
                task_id=invocation.task.task_id,
                product_scope=product_scope,
                requests=[item.request for item in results],
                specialist_artifacts=artifacts,
                evidence_context=evidence_context,
                output=CompetitorSynthesisModelOutput.model_validate(result.output),
            )
        except CompetitorSynthesisValidationError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                str(exc),
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details=exc.details,
            ) from exc

    @staticmethod
    def _runtime_error(
        invocation: AgentInvocation, error: ModelGatewayError
    ) -> RuntimeGatewayError:
        if error.code is ModelErrorCode.TIMEOUT:
            runtime_code = RuntimeErrorCode.TIMEOUT
        elif error.code is ModelErrorCode.CANCELLED:
            runtime_code = RuntimeErrorCode.CANCELLED
        elif error.code in {
            ModelErrorCode.MODEL_NOT_FOUND,
            ModelErrorCode.MODEL_DISABLED,
            ModelErrorCode.CREDENTIAL_MISSING,
            ModelErrorCode.AUTHENTICATION_FAILED,
            ModelErrorCode.PROVIDER_NOT_BOUND,
            ModelErrorCode.CAPABILITY_MISSING,
        }:
            runtime_code = RuntimeErrorCode.DEPENDENCY_MISSING
        elif error.code is ModelErrorCode.STRUCTURED_OUTPUT_INVALID:
            runtime_code = RuntimeErrorCode.SCHEMA_INVALID
        else:
            runtime_code = RuntimeErrorCode.ADAPTER_FAILED
        return RuntimeGatewayError(
            runtime_code,
            "Competitor synthesis model call failed.",
            agent_run_id=invocation.agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )


def can_synthesize(results: list[SpecialistTaskResult]) -> bool:
    artifacts: list[CompetitorSpecialistArtifact] = [
        result.artifact for result in results if result.artifact is not None
    ]
    return (
        len(artifacts) == 3
        and len({artifact.specialist_type for artifact in artifacts}) == 3
        and all(artifact.findings for artifact in artifacts)
    )
