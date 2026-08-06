"""将内部 LangGraph Agent 调用桥接到统一 Model Gateway。"""

import json

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
from app.workflows.contracts import ResearchArtifact


class InternalModelAgentAdapter:
    """不携带业务 Prompt；只解析未来业务分支显式注册的 Prompt。"""

    adapter_type = "internal_model"

    def __init__(
        self,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        selection_resolver: ProjectModelSelectionResolver,
    ) -> None:
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.selection_resolver = selection_resolver

    async def execute(self, invocation: AgentInvocation) -> object:
        invocation.cancellation_token.raise_if_cancelled()
        try:
            model_id = await self.selection_resolver.resolve(
                invocation.task.project_id, invocation.task.agent_type
            )
            prompt_key = f"agent:{invocation.task.agent_type.value}"
            prompt = self.prompt_registry.resolve(prompt_key)
            rendered = prompt.render(self._prompt_variables(invocation))
        except (ModelSelectionResolutionError, PromptRegistryError) as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "内部模型 Agent 缺少模型策略或 Prompt 配置。",
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
                    response_model=ResearchArtifact,
                    timeout_seconds=float(invocation.task.budget.deadline_seconds),
                )
            )
        except ModelGatewayError as exc:
            raise self._runtime_error(invocation, exc) from exc
        invocation.cancellation_token.raise_if_cancelled()
        return result.output

    @staticmethod
    def _prompt_variables(invocation: AgentInvocation) -> dict[str, str]:
        return {
            "project_id": invocation.task.project_id,
            "task_id": invocation.task.task_id,
            "agent_type": invocation.task.agent_type.value,
            "goal": invocation.task.goal,
            "scope_json": json.dumps(
                invocation.task.scope, ensure_ascii=False, sort_keys=True
            ),
            "brief_json": invocation.context.brief.model_dump_json(),
            "upstream_artifacts_json": json.dumps(
                {
                    key: value.model_dump(mode="json")
                    for key, value in invocation.context.upstream_artifacts.items()
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "decision_history_json": json.dumps(
                [item.model_dump(mode="json") for item in invocation.context.decision_history],
                ensure_ascii=False,
                sort_keys=True,
            ),
            "iteration": str(invocation.context.iteration),
        }

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
            "内部模型 Agent 调用失败。",
            agent_run_id=invocation.agent_run_id,
            retryable=error.retryable,
            details={"model_error_code": error.code},
        )
