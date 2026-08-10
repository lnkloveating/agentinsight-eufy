"""Model adapter for competitor ecosystem synthesis after three A2A fact specialists."""

from __future__ import annotations

import json

from app.agents.competitor.ecosystem_contracts import CompetitorEcosystemModelOutput
from app.agents.competitor.ecosystem_prompt import COMPETITOR_ECOSYSTEM_PROMPT_KEY
from app.agents.competitor.ecosystem_validation import (
    CompetitorEcosystemOutputValidator,
    CompetitorEcosystemValidationError,
    build_blocked_ecosystem_artifact,
)
from app.application.evidence import EvidenceRetrievalService
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
from app.workflows.contracts import (
    ResearchAgentType,
    ResearchArtifact,
)


class CompetitorEcosystemModelAdapter:
    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        *,
        model_timeout_seconds: float = 180,
        validator: CompetitorEcosystemOutputValidator | None = None,
    ) -> None:
        if model_timeout_seconds <= 0:
            raise ValueError("model_timeout_seconds must be positive")
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.model_timeout_seconds = model_timeout_seconds
        self.validator = validator or CompetitorEcosystemOutputValidator()

    async def synthesize(
        self,
        invocation: AgentInvocation,
        results: list[SpecialistTaskResult],
        product_fact_synthesis: ResearchArtifact,
    ) -> ResearchArtifact:
        invocation.cancellation_token.raise_if_cancelled()
        evidence_context = invocation.context.evidence_context
        if evidence_context is None:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                "Competitor ecosystem synthesis requires the parent Evidence Context.",
                agent_run_id=invocation.agent_run_id,
                retryable=False,
            )
        artifacts = [result.artifact for result in results if result.artifact is not None]
        product_scope = list(dict.fromkeys(results[0].request.product_scope)) if results else []
        brief = invocation.context.brief
        ecosystem_scope = {
            "target": brief.target_ecosystems,
            "comparison": brief.comparison_ecosystems,
        }
        allowed_ids = {
            evidence_id for artifact in artifacts for evidence_id in artifact.evidence_ids
        }
        try:
            model_id = await self.selection_resolver.resolve(
                invocation.task.project_id, ResearchAgentType.COMPETITOR_RESEARCH
            )
            prompt = self.prompt_registry.resolve(COMPETITOR_ECOSYSTEM_PROMPT_KEY)
            rendered = prompt.render(
                {
                    "project_id": invocation.task.project_id,
                    "task_id": invocation.task.task_id,
                    "brief_json": brief.model_dump_json(),
                    "ecosystem_scope_json": json.dumps(
                        ecosystem_scope, ensure_ascii=False, sort_keys=True
                    ),
                    "product_scope_json": json.dumps(product_scope, ensure_ascii=False),
                    "product_fact_synthesis_json": json.dumps(
                        product_fact_synthesis.payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
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
                            if item.evidence_id in allowed_ids
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        except (ModelSelectionResolutionError, PromptRegistryError) as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "Competitor ecosystem synthesis lacks model or Prompt configuration.",
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
                    response_model=CompetitorEcosystemModelOutput,
                    timeout_seconds=self.model_timeout_seconds,
                    max_output_tokens=14_000,
                    provider_options={"temperature": 0.1, "thinking": {"type": "disabled"}},
                )
            )
        except ModelGatewayError as exc:
            raise self._runtime_error(invocation, exc) from exc
        try:
            return self.validator.validate(
                artifact_id=f"artifact_pending_{invocation.agent_run_id}",
                task_id=invocation.task.task_id,
                target_ecosystems=brief.target_ecosystems,
                comparison_ecosystems=brief.comparison_ecosystems,
                product_scope=product_scope,
                specialist_artifacts=artifacts,
                product_fact_synthesis=product_fact_synthesis,
                evidence_context=evidence_context,
                output=CompetitorEcosystemModelOutput.model_validate(result.output),
            )
        except CompetitorEcosystemValidationError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                str(exc),
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details=exc.details,
            ) from exc

    def build_blocked(
        self,
        invocation: AgentInvocation,
        results: list[SpecialistTaskResult],
    ) -> ResearchArtifact:
        artifacts: list[CompetitorSpecialistArtifact] = [
            result.artifact for result in results if result.artifact is not None
        ]
        product_scope = list(dict.fromkeys(results[0].request.product_scope)) if results else []
        context = (
            invocation.context.evidence_context
            or EvidenceRetrievalService.empty_context()
        )
        return build_blocked_ecosystem_artifact(
            artifact_id=f"artifact_pending_{invocation.agent_run_id}",
            task_id=invocation.task.task_id,
            target_ecosystems=invocation.context.brief.target_ecosystems,
            comparison_ecosystems=invocation.context.brief.comparison_ecosystems,
            product_scope=product_scope,
            specialist_artifacts=artifacts,
            evidence_context=context,
            reason="The three fact specialists did not provide enough findings for synthesis.",
        )

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
            "Competitor ecosystem synthesis model call failed.",
            agent_run_id=invocation.agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )
