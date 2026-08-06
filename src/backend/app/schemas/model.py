"""公开的模型目录与选择契约。"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class ModelCapability(StrEnum):
    TEXT = "text"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"
    TOOLS = "tools"
    REASONING = "reasoning"


class ModelSelection(BaseModel):
    """项目默认模型及可选的 Agent 级覆盖。"""

    default_model_id: str = Field(min_length=3, max_length=120)
    agent_overrides: dict[str, str] = Field(default_factory=dict)

    @field_validator("agent_overrides")
    @classmethod
    def validate_overrides(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not key.strip() for key in value):
            raise ValueError("agent override key cannot be blank")
        if any(len(model_id) < 3 or len(model_id) > 120 for model_id in value.values()):
            raise ValueError("agent override model id length is invalid")
        return value


class ModelSummary(BaseModel):
    """可安全返回给前端的模型信息，不含 Provider 凭据。"""

    model_id: str
    provider: str
    display_name: str
    capabilities: list[ModelCapability]
    enabled: bool
    credential_available: bool
    context_window: int | None = Field(default=None, ge=1)
    input_cost_microusd_per_million_tokens: int | None = Field(default=None, ge=0)
    output_cost_microusd_per_million_tokens: int | None = Field(default=None, ge=0)


class ModelPage(BaseModel):
    items: list[ModelSummary]
    default_model_id: str | None = None
