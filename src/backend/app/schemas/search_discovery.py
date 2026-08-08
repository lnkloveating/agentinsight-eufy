"""公开来源搜索发现的 API 契约。"""

import re
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class SearchDiscoveryIntent(StrEnum):
    COMPETITOR_CANDIDATE = "competitor_candidate"
    OFFICIAL_PRODUCT = "official_product"
    PRICE_CHANNEL = "price_channel"
    USER_REVIEW = "user_review"
    GENERAL = "general"


class SearchDiscoveryRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class SearchDiscoveryEvidenceStatus(StrEnum):
    CANDIDATE_ONLY = "candidate_only"


class SearchDiscoveryCreate(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    intent: SearchDiscoveryIntent
    provider_id: str = Field(default="tavily", min_length=1, max_length=80)
    max_results: int = Field(default=10, ge=1, le=20)
    include_domains: list[str] = Field(default_factory=list, max_length=20)
    exclude_domains: list[str] = Field(default_factory=list, max_length=20)
    requested_by: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)

    @field_validator("query", "requested_by", "purpose", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("provider_id", mode="before")
    @classmethod
    def normalize_provider_id(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("include_domains", "exclude_domains")
    @classmethod
    def normalize_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip().rstrip(".").lower()
            parts = urlsplit(f"//{candidate}")
            if (
                not candidate
                or parts.hostname != candidate
                or parts.port is not None
                or re.fullmatch(
                    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
                    r"(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})",
                    candidate,
                )
                is None
            ):
                raise ValueError("search discovery domains must be plain public hostnames")
            normalized.append(candidate)
        if len(normalized) != len(set(normalized)):
            raise ValueError("search discovery domains must be unique")
        return normalized

    @model_validator(mode="after")
    def domain_filters_must_not_overlap(self) -> "SearchDiscoveryCreate":
        if set(self.include_domains) & set(self.exclude_domains):
            raise ValueError("included and excluded search domains must not overlap")
        return self


class SearchDiscoveryCandidate(BaseModel):
    candidate_id: str
    rank: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    source_url: HttpUrl
    normalized_source_url: HttpUrl
    source_domain: str = Field(min_length=1, max_length=253)
    snippet: str = Field(max_length=2_000)
    score: float | None = Field(default=None, ge=0, le=1)
    evidence_status: SearchDiscoveryEvidenceStatus = (
        SearchDiscoveryEvidenceStatus.CANDIDATE_ONLY
    )


class SearchDiscoveryRun(BaseModel):
    search_discovery_run_id: str
    project_id: str
    provider_id: str
    status: SearchDiscoveryRunStatus
    query: str
    intent: SearchDiscoveryIntent
    max_results: int = Field(ge=1, le=20)
    include_domains: list[str]
    exclude_domains: list[str]
    candidates: list[SearchDiscoveryCandidate]
    result_count: int = Field(ge=0, le=20)
    provider_request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    requested_by: str
    purpose: str
    created_at: datetime
    completed_at: datetime | None = None


class SearchDiscoveryRunPage(BaseModel):
    items: list[SearchDiscoveryRun]
    total: int = Field(ge=0)
