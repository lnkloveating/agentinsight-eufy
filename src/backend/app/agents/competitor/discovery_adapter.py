"""通过统一 Model Gateway 运行竞品候选发现 Prompt。"""

import json

from app.agents.competitor.discovery_contracts import (
    CompetitorDiscoveryInputContext,
    CompetitorDiscoveryModelOutput,
)
from app.agents.competitor.discovery_prompt import COMPETITOR_DISCOVERY_PROMPT_KEY
from app.agents.competitor.discovery_validation import (
    CompetitorDiscoveryOutputValidator,
    CompetitorDiscoveryValidationError,
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
from app.workflows.contracts import ResearchAgentType


class CompetitorDiscoveryModelAgentAdapter:
    adapter_type = "competitor_discovery_internal_model"

    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        *,
        model_timeout_seconds: float = 180,
        validator: CompetitorDiscoveryOutputValidator | None = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.model_timeout_seconds = model_timeout_seconds
        self.validator = validator or CompetitorDiscoveryOutputValidator()

    async def execute(self, invocation: AgentInvocation) -> object:
        invocation.cancellation_token.raise_if_cancelled()
        try:
            context = CompetitorDiscoveryInputContext.model_validate(
                invocation.task.scope["discovery_context"]
            )
            model_id = await self.selection_resolver.resolve(
                invocation.task.project_id, ResearchAgentType.COMPETITOR_RESEARCH
            )
            prompt = self.prompt_registry.resolve(COMPETITOR_DISCOVERY_PROMPT_KEY)
            rendered = prompt.render(
                {
                    "project_id": invocation.task.project_id,
                    "task_id": invocation.task.task_id,
                    "brief_json": invocation.context.brief.model_dump_json(),
                    "discovery_context_json": json.dumps(
                        context.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "minimum_candidates": str(context.minimum_candidates),
                }
            )
        except (KeyError, ValueError, ModelSelectionResolutionError, PromptRegistryError) as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "竞品候选发现 Agent 缺少受控上下文、模型策略或 Prompt。",
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
                    response_model=CompetitorDiscoveryModelOutput,
                    timeout_seconds=self.model_timeout_seconds,
                    max_output_tokens=6_000,
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
                invocation.task,
                context,
                CompetitorDiscoveryModelOutput.model_validate(result.output),
            )
        except CompetitorDiscoveryValidationError as exc:
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
            "竞品候选发现模型调用失败。",
            agent_run_id=invocation.agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )
