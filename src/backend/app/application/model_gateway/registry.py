"""模型 Provider 的显式注册表。"""

from app.application.model_gateway.contracts import ModelProvider


class ModelProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider, *, replace: bool = False) -> None:
        provider_id = provider.provider_id.strip().lower()
        if not provider_id:
            raise ValueError("provider_id cannot be empty")
        if provider_id in self._providers and not replace:
            raise ValueError(f"provider already registered: {provider_id}")
        self._providers[provider_id] = provider

    def resolve(self, provider_id: str) -> ModelProvider | None:
        return self._providers.get(provider_id.strip().lower())

    def providers(self) -> tuple[ModelProvider, ...]:
        return tuple(self._providers.values())
