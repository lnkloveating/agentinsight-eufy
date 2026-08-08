"""通过 Model Gateway 执行官方产品情报 Prompt 的 A2A 专家 Adapter。"""

from __future__ import annotations

import hashlib
import json

from app.agents.competitor.official_product_contracts import OfficialProductModelOutput
from app.agents.competitor.official_product_prompt import OFFICIAL_PRODUCT_PROMPT_KEY
from app.agents.competitor.official_product_validation import (
    OfficialProductOutputValidator,
    OfficialProductValidationError,
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
from app.application.runtime import RuntimeErrorCode, RuntimeGatewayError
from app.integrations.a2a import A2ASpecialistInvocation, CompetitorSpecialistArtifact
from app.schemas.evidence import EvidenceClaimType, EvidenceStatus
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchAgentType,
)


class OfficialProductModelSpecialistAdapter:
    adapter_type = "competitor_official_product_internal_model"

    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        *,
        model_timeout_seconds: float = 180,
        validator: OfficialProductOutputValidator | None = None,
    ) -> None:
        if model_timeout_seconds <= 0:
            raise ValueError("model_timeout_seconds must be positive")
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.model_timeout_seconds = model_timeout_seconds
        self.validator = validator or OfficialProductOutputValidator()

    async def execute(
        self,
        invocation: A2ASpecialistInvocation,
    ) -> CompetitorSpecialistArtifact:
        invocation.cancellation_token.raise_if_cancelled()
        evidence_context = self._eligible_context(invocation.context.evidence_context)
        if not evidence_context.items:
            return self.validator.build_blocked(
                a2a_task_id=invocation.a2a_task_id,
                request=invocation.request,
                evidence_context=evidence_context,
            )

        try:
            model_id = await self.selection_resolver.resolve(
                invocation.request.project_id,
                ResearchAgentType.COMPETITOR_RESEARCH,
            )
            prompt = self.prompt_registry.resolve(OFFICIAL_PRODUCT_PROMPT_KEY)
            rendered = prompt.render(
                {
                    "project_id": invocation.request.project_id,
                    "parent_task_id": invocation.request.parent_task_id,
                    "a2a_task_id": invocation.a2a_task_id,
                    "brief_json": invocation.context.brief.model_dump_json(),
                    "evidence_request_json": invocation.request.model_dump_json(),
                    "evidence_context_json": json.dumps(
                        evidence_context.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        except (ModelSelectionResolutionError, PromptRegistryError) as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "官方产品专家缺少模型策略或 Prompt 配置。",
                agent_run_id=invocation.parent_agent_run_id,
                retryable=False,
                details={"configuration_error": getattr(exc, "code", type(exc).__name__)},
            ) from exc

        try:
            result = await self.model_gateway.generate(
                ModelRequest(
                    project_id=invocation.request.project_id,
                    agent_run_id=invocation.parent_agent_run_id,
                    trace_id=invocation.trace_id,
                    model_id=model_id,
                    prompt_key=prompt.prompt_key,
                    prompt_version=prompt.version,
                    messages=(
                        ModelMessage(role="system", content=rendered.system),
                        ModelMessage(role="user", content=rendered.user),
                    ),
                    response_model=OfficialProductModelOutput,
                    timeout_seconds=self.model_timeout_seconds,
                    max_output_tokens=8_000,
                    provider_options={
                        "temperature": 0.1,
                        "thinking": {"type": "disabled"},
                    },
                )
            )
        except ModelGatewayError as exc:
            raise self._runtime_error(invocation, exc) from exc

        invocation.cancellation_token.raise_if_cancelled()
        try:
            return self.validator.validate(
                a2a_task_id=invocation.a2a_task_id,
                request=invocation.request,
                evidence_context=evidence_context,
                output=OfficialProductModelOutput.model_validate(result.output),
            )
        except OfficialProductValidationError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                str(exc),
                agent_run_id=invocation.parent_agent_run_id,
                retryable=False,
                details=exc.details,
            ) from exc

    @staticmethod
    def _eligible_context(
        context: AgentEvidenceContext | None,
    ) -> AgentEvidenceContext:
        eligible = [
            item
            for item in (context.items if context is not None else [])
            if item.status
            in {
                EvidenceStatus.VERIFIED.value,
                EvidenceStatus.PARTIALLY_VERIFIED.value,
            }
            and item.claim_type
            in {
                EvidenceClaimType.VENDOR_CLAIM.value,
                EvidenceClaimType.FACT.value,
            }
        ]
        return AgentEvidenceContext(
            items=eligible,
            available_evidence_count=len(eligible),
            included_evidence_count=len(eligible),
            omitted_evidence_count=0,
            context_hash=OfficialProductModelSpecialistAdapter._context_hash(eligible),
        )

    @staticmethod
    def _context_hash(items: list[AgentEvidence]) -> str:
        canonical = json.dumps(
            [item.model_dump(mode="json") for item in items],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _runtime_error(
        invocation: A2ASpecialistInvocation,
        error: ModelGatewayError,
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
            "官方产品专家模型调用失败。",
            agent_run_id=invocation.parent_agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )
