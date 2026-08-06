"""模型目录、Provider 与调用层共享的内部契约。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from app.schemas.model import ModelCapability


class ModelDefinition(BaseModel):
    """从环境配置加载的内部模型定义。"""

    model_id: str = Field(min_length=3, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    provider_model: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=120)
    credential_env: str = Field(min_length=1, max_length=120)
    capabilities: list[ModelCapability] = Field(default_factory=list)
    enabled: bool = True
    context_window: int | None = Field(default=None, ge=1)
    input_cost_microusd_per_million_tokens: int | None = Field(default=None, ge=0)
    output_cost_microusd_per_million_tokens: int | None = Field(default=None, ge=0)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_id", "provider")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("identifier cannot be blank")
        return normalized

    @field_validator("credential_env")
    @classmethod
    def validate_credential_env(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.replace("_", "").isalnum() or not normalized[0].isalpha():
            raise ValueError("credential_env must be an environment variable name")
        return normalized.upper()

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(
        cls, value: list[ModelCapability]
    ) -> list[ModelCapability]:
        return list(dict.fromkeys(value))


class CredentialResolver(Protocol):
    def available(self, env_name: str) -> bool: ...

    def resolve(self, env_name: str) -> str | None: ...


class EnvironmentCredentialResolver:
    """只按配置的变量名读取密钥，绝不返回到公开模型目录。"""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        if environment is None:
            import os

            environment = os.environ
        self._environment = environment

    def available(self, env_name: str) -> bool:
        return bool(self.resolve(env_name))

    def resolve(self, env_name: str) -> str | None:
        value = self._environment.get(env_name)
        stripped = value.strip() if value is not None else ""
        return stripped or None


class ModelErrorCode(StrEnum):
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_DISABLED = "model_disabled"
    CREDENTIAL_MISSING = "credential_missing"
    PROVIDER_NOT_BOUND = "provider_not_bound"
    CAPABILITY_MISSING = "capability_missing"
    TIMEOUT = "timeout"
    PROVIDER_FAILED = "provider_failed"
    RATE_LIMITED = "rate_limited"
    STRUCTURED_OUTPUT_INVALID = "structured_output_invalid"
    CANCELLED = "cancelled"


class ModelGatewayError(RuntimeError):
    def __init__(
        self,
        code: ModelErrorCode,
        message: str,
        *,
        retryable: bool,
        model_call_id: str | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.model_call_id = model_call_id
        super().__init__(message)


class ModelProviderError(RuntimeError):
    def __init__(
        self,
        code: ModelErrorCode,
        message: str,
        *,
        retryable: bool,
        provider_request_id: str | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.provider_request_id = provider_request_id
        super().__init__(message)


@dataclass(frozen=True)
class ModelMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ModelRequest:
    project_id: str
    agent_run_id: str
    trace_id: str
    model_id: str
    prompt_key: str
    prompt_version: str
    messages: tuple[ModelMessage, ...]
    response_model: type[BaseModel]
    timeout_seconds: float = 60.0
    max_output_tokens: int | None = None
    provider_options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderModelRequest:
    provider_model: str
    credential: str
    messages: tuple[ModelMessage, ...]
    response_schema: dict[str, Any]
    timeout_seconds: float
    max_output_tokens: int | None
    options: Mapping[str, Any]


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token usage cannot be negative")


@dataclass(frozen=True)
class ProviderModelResult:
    output: object
    usage: ModelUsage = ModelUsage()
    provider_request_id: str | None = None


@dataclass(frozen=True)
class ModelResult:
    output: BaseModel
    model_id: str
    provider: str
    usage: ModelUsage
    estimated_cost_microusd: int
    model_call_id: str
    attempt_count: int


class ModelProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult: ...
