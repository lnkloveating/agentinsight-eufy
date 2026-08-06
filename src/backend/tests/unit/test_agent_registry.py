import pytest

from app.application.runtime import AgentInvocation, AgentRegistry, CancellationToken
from app.workflows.contracts import ResearchAgentType


class Adapter:
    def __init__(self, adapter_type: str) -> None:
        self._adapter_type = adapter_type

    @property
    def adapter_type(self) -> str:
        return self._adapter_type

    async def execute(self, invocation: AgentInvocation) -> object:
        return invocation


def test_registry_requires_explicit_replace_and_supports_unbind() -> None:
    registry = AgentRegistry()
    first = Adapter("internal")
    second = Adapter("external")

    registry.bind(ResearchAgentType.USER_RESEARCH, first)
    with pytest.raises(ValueError, match="already bound"):
        registry.bind(ResearchAgentType.USER_RESEARCH, second)

    registry.bind(ResearchAgentType.USER_RESEARCH, second, replace=True)
    binding = registry.resolve(ResearchAgentType.USER_RESEARCH)
    assert binding is not None
    assert binding.adapter_type == "external"
    assert len(registry.bindings()) == 1

    registry.unbind(ResearchAgentType.USER_RESEARCH)
    assert registry.resolve(ResearchAgentType.USER_RESEARCH) is None


def test_registry_rejects_blank_adapter_type_and_token_is_explicit() -> None:
    registry = AgentRegistry()
    with pytest.raises(ValueError, match="cannot be empty"):
        registry.bind(ResearchAgentType.RED_TEAM, Adapter("  "))

    token = CancellationToken()
    assert token.cancelled is False
    token.cancel()
    assert token.cancelled is True
