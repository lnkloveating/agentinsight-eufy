from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CollectionJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceLocatorKind(StrEnum):
    TEXT = "text"
    PAGE = "page"
    ROW = "row"
    JSON = "json"


class SourceFragmentVerificationStatus(StrEnum):
    VERIFIED = "verified"
    INVALID = "invalid"


class SourceLocator(BaseModel):
    kind: SourceLocatorKind
    page_number: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    row_number: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)
    json_pointer: str | None = None

    @model_validator(mode="after")
    def validate_locator_shape(self) -> "SourceLocator":
        if self.char_start is None or self.char_end is None:
            raise ValueError("source locator requires a character range")
        if self.char_end <= self.char_start:
            raise ValueError("source locator character range is invalid")
        if self.kind is SourceLocatorKind.PAGE and self.page_number is None:
            raise ValueError("page locator requires page_number")
        if self.kind is SourceLocatorKind.ROW and self.row_number is None:
            raise ValueError("row locator requires row_number")
        if self.kind is SourceLocatorKind.JSON and self.json_pointer is None:
            raise ValueError("JSON locator requires json_pointer")
        if self.line_start is not None and self.line_end is not None:
            if self.line_end < self.line_start:
                raise ValueError("source locator line range is invalid")
        return self


class SourceProcessingJob(BaseModel):
    collection_job_id: str
    project_id: str
    source_asset_id: str
    source_type: str
    status: CollectionJobStatus
    attempt_count: int = Field(ge=0)
    progress: int = Field(ge=0, le=100)
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ParsedArtifact(BaseModel):
    parsed_artifact_id: str
    project_id: str
    source_asset_id: str
    collection_job_id: str
    parser_id: str
    parser_version: str
    source_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fragment_count: int = Field(ge=0)
    created_at: datetime


class SourceFragment(BaseModel):
    source_fragment_id: str
    parsed_artifact_id: str
    project_id: str
    source_asset_id: str
    ordinal: int = Field(ge=0)
    locator: SourceLocator
    original_excerpt: str = Field(min_length=1)
    excerpt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    verification_status: SourceFragmentVerificationStatus
    created_at: datetime


class SourceFragmentPage(BaseModel):
    items: list[SourceFragment]
    next_cursor: str | None = None
    total: int = Field(ge=0)


class SourceProcessingStatus(BaseModel):
    job: SourceProcessingJob
    parsed_artifact: ParsedArtifact | None = None
