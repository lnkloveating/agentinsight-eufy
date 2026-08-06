"""工作流与后续内部模型、外部 Runtime 和 A2A 网关之间的边界。"""

from typing import Protocol

from app.workflows.contracts import AgentContext, ResearchArtifact, ResearchTask


class AgentRuntime(Protocol):
    async def execute(
        self,
        task: ResearchTask,
        context: AgentContext,
    ) -> ResearchArtifact: ...


class AgentRuntimeNotBoundError(RuntimeError):
    pass


class UnboundAgentRuntime:
    """生产安全默认值：未绑定真实 Runtime 时明确失败，不生成占位研究。"""

    async def execute(
        self,
        task: ResearchTask,
        context: AgentContext,
    ) -> ResearchArtifact:
        del context
        raise AgentRuntimeNotBoundError(
            f"AGENT_RUNTIME_NOT_BOUND:{task.agent_type}:{task.task_id}"
        )
