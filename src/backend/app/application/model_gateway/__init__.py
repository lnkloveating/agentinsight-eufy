"""多模型目录与模型调用网关。"""

from app.application.model_gateway.catalog import ModelCatalog, ModelCatalogError
from app.application.model_gateway.contracts import (
    CredentialResolver,
    EnvironmentCredentialResolver,
    ModelDefinition,
    ModelErrorCode,
    ModelGatewayError,
    ModelMessage,
    ModelProvider,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelUsage,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.application.model_gateway.gateway import ModelGateway
from app.application.model_gateway.prompts import (
    PromptDefinition,
    PromptRegistry,
    PromptRegistryError,
    RenderedPrompt,
)
from app.application.model_gateway.providers import (
    OpenAICompatibleProvider,
    OpenAICompatibleProviderConfig,
    parse_openai_compatible_provider_configs,
)
from app.application.model_gateway.registry import ModelProviderRegistry
from app.application.model_gateway.selection import (
    ModelSelectionResolutionError,
    ProjectModelSelectionResolver,
)

__all__ = [
    "CredentialResolver",
    "EnvironmentCredentialResolver",
    "ModelCatalog",
    "ModelCatalogError",
    "ModelDefinition",
    "ModelErrorCode",
    "ModelGateway",
    "ModelGatewayError",
    "ModelMessage",
    "ModelProvider",
    "ModelProviderError",
    "ModelProviderRegistry",
    "ModelRequest",
    "ModelResult",
    "ModelSelectionResolutionError",
    "ModelUsage",
    "OpenAICompatibleProvider",
    "OpenAICompatibleProviderConfig",
    "PromptDefinition",
    "PromptRegistry",
    "PromptRegistryError",
    "ProviderModelRequest",
    "ProviderModelResult",
    "ProjectModelSelectionResolver",
    "RenderedPrompt",
    "parse_openai_compatible_provider_configs",
]
