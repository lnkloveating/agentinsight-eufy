"""Source Fragment 到 Evidence Lake 的批次审核契约。"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.evidence import Evidence, EvidenceClaimType
from app.schemas.source_processing import SourceFragment
from app.schemas.source_requirements import (
    CompetitorResearchDimension,
    ProductReference,
    ProductRole,
)
from app.schemas.source_routing import SourceRouteTarget


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FragmentEvidenceBatchStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    REJECTED = "rejected"


class FragmentEvidenceEligibility(StrEnum):
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    ALREADY_PROMOTED = "already_promoted"


class FragmentEvidencePromotionStatus(StrEnum):
    NOT_SELECTED = "not_selected"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FragmentEvidenceDecisionAction(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"


class FragmentEvidenceBatchCreate(StrictModel):
    source_asset_ids: list[str] = Field(min_length=1, max_length=50)
    source_fragment_ids: list[str] = Field(default_factory=list, max_length=200)
    requested_by: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)

    @field_validator("source_asset_ids", "source_fragment_ids")
    @classmethod
    def unique_asset_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("source/fragment IDs must be non-empty and unique")
        return normalized

    @field_validator("requested_by", "purpose", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class FragmentEvidenceQualityPrior(StrictModel):
    policy_version: str
    confidence: float = Field(ge=0, le=1)
    authority_score: float = Field(ge=0, le=1)
    recency_score: float = Field(ge=0, le=1)
    diversity_score: float = Field(ge=0, le=1)
    reasons: list[str]


class FragmentEvidenceDecisionSelection(StrictModel):
    fragment_evidence_item_id: str = Field(min_length=1, max_length=40)
    claim_type: EvidenceClaimType
    published_at: datetime | None = None
    user_segment: str | None = Field(default=None, max_length=160)

    @field_validator("fragment_evidence_item_id", "user_segment", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("published_at")
    @classmethod
    def published_at_not_in_future(cls, value: datetime | None) -> datetime | None:
        comparable = (
            value.replace(tzinfo=UTC)
            if value is not None and value.tzinfo is None
            else value
        )
        if comparable is not None and comparable > datetime.now(UTC):
            raise ValueError("published_at must not be in the future")
        return value


class FragmentEvidenceDecisionCreate(StrictModel):
    action: FragmentEvidenceDecisionAction
    selections: list[FragmentEvidenceDecisionSelection] = Field(
        default_factory=list, max_length=200
    )
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1_000)

    @field_validator("actor", "reason", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_gate(self) -> "FragmentEvidenceDecisionCreate":
        item_ids = [item.fragment_evidence_item_id for item in self.selections]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("fragment evidence decision items must be unique")
        if self.action is FragmentEvidenceDecisionAction.CONFIRM and not self.selections:
            raise ValueError("confirm requires at least one selected Evidence Draft")
        if self.action is FragmentEvidenceDecisionAction.REJECT and self.selections:
            raise ValueError("reject cannot select Evidence Drafts")
        return self


class FragmentEvidenceDecision(StrictModel):
    fragment_evidence_decision_id: str
    action: FragmentEvidenceDecisionAction
    selected_item_ids: list[str]
    actor: str
    reason: str
    created_at: datetime


class FragmentEvidenceBatchItem(StrictModel):
    fragment_evidence_item_id: str
    source_asset_id: str
    source_fragment: SourceFragment
    eligibility: FragmentEvidenceEligibility
    block_reasons: list[str]
    confirmed_routes: list[SourceRouteTarget]
    allowed_claim_types: list[EvidenceClaimType]
    suggested_claim_type: EvidenceClaimType | None
    product_role: ProductRole | None
    product: ProductReference | None
    dimensions: list[CompetitorResearchDimension]
    region: str | None
    quality_prior: FragmentEvidenceQualityPrior
    existing_evidence_id: str | None
    selected: bool
    selected_claim_type: EvidenceClaimType | None
    published_at: datetime | None
    user_segment: str | None
    promotion_status: FragmentEvidencePromotionStatus
    evidence: Evidence | None
    error_code: str | None


class FragmentEvidenceBatch(StrictModel):
    fragment_evidence_batch_id: str
    project_id: str
    status: FragmentEvidenceBatchStatus
    source_asset_ids: list[str]
    policy_version: str
    input_hash: str
    items: list[FragmentEvidenceBatchItem]
    eligible_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    already_promoted_count: int = Field(ge=0)
    promoted_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    decision: FragmentEvidenceDecision | None
    requested_by: str
    purpose: str
    created_at: datetime
    updated_at: datetime


class FragmentEvidenceBatchPage(StrictModel):
    items: list[FragmentEvidenceBatch]
    total: int = Field(ge=0)


class FragmentEvidenceDecisionResult(StrictModel):
    batch: FragmentEvidenceBatch
    decision_created: bool
