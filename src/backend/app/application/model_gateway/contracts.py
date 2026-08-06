"""模型目录、Provider 与调用层共享的内部契约。"""

from __future__ import annotations

from collections.abc import Mapping
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
