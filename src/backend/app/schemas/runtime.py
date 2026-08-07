from enum import StrEnum

from pydantic import BaseModel, Field


class RuntimeCapability(StrEnum):
    TEXT = "text"
    STRUCTURED_OUTPUT = "structured_output"
    LOCAL_FILES = "local_files"
    WEBPAGE = "webpage"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class RuntimeUnavailableReason(StrEnum):
    DISABLED = "disabled"
    EXECUTABLE_MISSING = "executable_missing"
    CREDENTIAL_MISSING = "credential_missing"
    PROBE_FAILED = "probe_failed"


class ExternalRuntimeSummary(BaseModel):
    runtime_id: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    adapter_type: str = "external_cli"
    capabilities: list[RuntimeCapability] = Field(default_factory=list)
    enabled: bool
    executable_available: bool
    credential_available: bool
    available: bool
    version: str | None = Field(default=None, max_length=200)
    unavailable_reason: RuntimeUnavailableReason | None = None
    model_id: str | None = Field(default=None, max_length=200)


class ExternalRuntimePage(BaseModel):
    items: list[ExternalRuntimeSummary]
