"""通过统一 Model Gateway 执行用户研究 Prompt 的真实内部模型 Adapter。"""

from __future__ import annotations

import json

from app.agents.user_research.contracts import UserResearchModelOutput
from app.agents.user_research.validation import (
    UserResearchOutputValidator,
    UserResearchValidationError,
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
from app.application.runtime.contracts import (
    AgentInvocation,
    RuntimeErrorCode,
    RuntimeGatewayError,
)


class UserResearchModelAgentAdapter:
    adapter_type = "user_research_internal_model"

    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
        validator: UserResearchOutputValidator | None = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver
        self.validator = validator or UserResearchOutputValidator()

    async def execute(self, invocation: AgentInvocation) -> object:
        invocation.cancellation_token.raise_if_cancelled()
        evidence_context = invocation.context.evidence_context
        if evidence_context is None or not evidence_context.items:
            if evidence_context is None:
                raise RuntimeGatewayError(
                    RuntimeErrorCode.DEPENDENCY_MISSING,
                    "用户研究 Agent 缺少 Evidence Context。",
                    agent_run_id=invocation.agent_run_id,
                    retryable=False,
                )
            return self.validator.build_blocked(invocation.task, evidence_context)

        try:
            model_id = await self.selection_resolver.resolve(
                invocation.task.project_id, invocation.task.agent_type
            )
            prompt = self.prompt_registry.resolve(
                f"agent:{invocation.task.agent_type.value}"
            )
            rendered = prompt.render(
                {
                    "project_id": invocation.task.project_id,
                    "task_id": invocation.task.task_id,
                    "iteration": str(invocation.context.iteration),
                    "goal": invocation.task.goal,
                    "brief_json": invocation.context.brief.model_dump_json(),
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
                "用户研究 Agent 缺少模型策略或 Prompt 配置。",
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
                    response_model=UserResearchModelOutput,
                    timeout_seconds=float(invocation.task.budget.deadline_seconds),
                    max_output_tokens=6_000,
                    provider_options={"temperature": 0.1},
                )
            )
        except ModelGatewayError as exc:
            raise self._runtime_error(invocation, exc) from exc

        invocation.cancellation_token.raise_if_cancelled()
        try:
            return self.validator.validate(
                invocation.task,
                evidence_context,
                UserResearchModelOutput.model_validate(result.output),
            )
        except UserResearchValidationError as exc:
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
            "用户研究模型调用失败。",
            agent_run_id=invocation.agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )
