from typing import Any

import pytest

from app.application.model_gateway import (
    ModelProviderRegistry,
    PromptDefinition,
    PromptRegistry,
    PromptRegistryError,
    ProviderModelRequest,
    ProviderModelResult,
)


class NoopProvider:
    provider_id = "test"

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        return ProviderModelResult(output={"request_model": request.provider_model})


def test_prompt_registry_renders_explicit_version_and_switches_active() -> None:
    registry = PromptRegistry()
    v1 = PromptDefinition("agent:test", "1", "System {scope}", "Question {question}")
    v2 = PromptDefinition("agent:test", "2", "System v2 {scope}", "Question {question}")
    registry.register(v1)
    registry.register(v2)

    rendered = registry.resolve("agent:test").render(
        {"scope": "home", "question": "what changed?"}
    )
    assert rendered.system == "System home"
    registry.activate("agent:test", "2")
    assert registry.resolve("agent:test").version == "2"


def test_prompt_registry_rejects_missing_or_complex_variables() -> None:
    definition = PromptDefinition("agent:test", "1", "System {scope}", "Question")
    with pytest.raises(PromptRegistryError, match="missing prompt variables"):
        definition.render({})
    with pytest.raises(PromptRegistryError, match="simple identifiers"):
        PromptDefinition("agent:test", "2", "System {scope.name}", "Question")


def test_provider_registry_requires_explicit_unique_binding() -> None:
    registry = ModelProviderRegistry()
    provider = NoopProvider()
    registry.register(provider)
    assert registry.resolve("TEST") is provider
    with pytest.raises(ValueError, match="already registered"):
        registry.register(provider)
    registry.register(provider, replace=True)
    assert registry.providers() == (provider,)


def test_noop_provider_signature_accepts_structured_request() -> None:
    annotations: dict[str, Any] = NoopProvider.generate.__annotations__
    assert annotations["request"] is ProviderModelRequest
