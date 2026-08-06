"""Agent 类型到执行 Adapter 的显式注册表。"""

from app.application.runtime.contracts import AdapterBinding, AgentAdapter
from app.workflows.contracts import ResearchAgentType


class AgentRegistry:
    def __init__(self) -> None:
        self._bindings: dict[ResearchAgentType, AdapterBinding] = {}

    def bind(
        self,
        agent_type: ResearchAgentType,
        adapter: AgentAdapter,
        *,
        replace: bool = False,
    ) -> None:
        if agent_type in self._bindings and not replace:
            raise ValueError(f"adapter already bound for {agent_type}")
        adapter_type = adapter.adapter_type.strip()
        if not adapter_type:
            raise ValueError("adapter_type cannot be empty")
        self._bindings[agent_type] = AdapterBinding(
            agent_type=agent_type,
            adapter_type=adapter_type,
            adapter=adapter,
        )

    def unbind(self, agent_type: ResearchAgentType) -> None:
        self._bindings.pop(agent_type, None)

    def resolve(self, agent_type: ResearchAgentType) -> AdapterBinding | None:
        return self._bindings.get(agent_type)

    def bindings(self) -> tuple[AdapterBinding, ...]:
        return tuple(self._bindings.values())
