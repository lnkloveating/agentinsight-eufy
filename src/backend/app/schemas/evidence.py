from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


class CollectionJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    OUTDATED = "outdated"
    MOCK = "mock"
    INVALID = "invalid"


class EvidenceClaimType(StrEnum):
    FACT = "fact"
    USER_OPINION = "user_opinion"
    VENDOR_CLAIM = "vendor_claim"
    AGENT_INFERENCE = "agent_inference"


class ClaimType(StrEnum):
    FACT = "fact"
    USER_OPINION = "user_opinion"
    VENDOR_CLAIM = "vendor_claim"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    MISSING_EVIDENCE = "missing_evidence"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class EvidenceRelationship(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class Evidence(BaseModel):
    evidence_id: str
    source_url: HttpUrl
    source_domain: str
    source_type: str
    title: str
    original_excerpt: str
    claim_type: EvidenceClaimType
    product: str | None = None
    region: str | None = None
    user_segment: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    status: EvidenceStatus
    content_hash: str
    confidence: float = Field(ge=0, le=1)
    authority_score: float = Field(ge=0, le=1)
    recency_score: float = Field(ge=0, le=1)
    diversity_score: float = Field(ge=0, le=1)


class EvidenceIngest(BaseModel):
    collection_job_id: str | None = None
    source_url: HttpUrl
    source_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1)
    original_excerpt: str = Field(min_length=1)
    claim_type: EvidenceClaimType
    product: str | None = Field(default=None, max_length=160)
    region: str | None = Field(default=None, max_length=120)
    user_segment: str | None = Field(default=None, max_length=160)
    published_at: datetime | None = None
    collected_at: datetime
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    confidence: float = Field(ge=0, le=1)
    authority_score: float = Field(ge=0, le=1)
    recency_score: float = Field(ge=0, le=1)
    diversity_score: float = Field(ge=0, le=1)


class EvidenceIngestResult(BaseModel):
    evidence: Evidence
    created: bool


class EvidencePage(BaseModel):
    items: list[Evidence]
    next_cursor: str | None = None
    total: int = Field(ge=0)


class Claim(BaseModel):
    claim_id: str
    statement: str
    claim_type: ClaimType
    evidence_ids: list[str]
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    status: ClaimStatus


class ClaimCreate(BaseModel):
    statement: str = Field(min_length=1)
    claim_type: ClaimType
    evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def evidence_relationships_must_not_overlap(self) -> "ClaimCreate":
        overlap = set(self.evidence_ids) & set(self.contradicting_evidence_ids)
        if overlap:
            raise ValueError("Evidence cannot both support and contradict the same Claim")
        return self


class ClaimGateResult(BaseModel):
    claim: Claim
    eligible_for_factual_use: bool
    rejected_evidence_ids: dict[str, str] = Field(default_factory=dict)
