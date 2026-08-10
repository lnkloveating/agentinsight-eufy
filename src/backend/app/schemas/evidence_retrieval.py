"""项目隔离的共享 Evidence 检索契约。"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.evidence import EvidenceClaimType, EvidenceStatus
from app.workflows.contracts import AgentEvidenceContext

SourceTypeFilter = Annotated[str, Field(min_length=1, max_length=80)]
IdentifierFilter = Annotated[str, Field(min_length=1, max_length=80)]
ProductFilter = Annotated[str, Field(min_length=1, max_length=160)]
RegionFilter = Annotated[str, Field(min_length=1, max_length=120)]
UserSegmentFilter = Annotated[str, Field(min_length=1, max_length=160)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRetrievalStrategy(StrEnum):
    METADATA_QUALITY = "metadata_quality"
    LEXICAL_METADATA = "lexical_metadata"
    EXACT_EVIDENCE_IDS = "exact_evidence_ids"


class EvidenceRetrievalQuery(StrictModel):
    consumer: str = Field(min_length=1, max_length=120)
    question: str | None = Field(default=None, min_length=1, max_length=2_000)
    statuses: list[EvidenceStatus] = Field(
        default_factory=lambda: [
            EvidenceStatus.VERIFIED,
            EvidenceStatus.PARTIALLY_VERIFIED,
        ],
        min_length=1,
        max_length=2,
    )
    claim_types: list[EvidenceClaimType] = Field(default_factory=list, max_length=30)
    source_types: list[SourceTypeFilter] = Field(default_factory=list, max_length=30)
    source_asset_ids: list[IdentifierFilter] = Field(default_factory=list, max_length=500)
    evidence_ids: list[IdentifierFilter] = Field(default_factory=list, max_length=500)
    products: list[ProductFilter] = Field(default_factory=list, max_length=100)
    regions: list[RegionFilter] = Field(default_factory=list, max_length=30)
    user_segments: list[UserSegmentFilter] = Field(default_factory=list, max_length=30)
    max_items: int = Field(default=30, ge=1, le=200)
    max_excerpt_chars: int = Field(default=2_000, ge=1, le=10_000)
    max_total_chars: int = Field(default=40_000, ge=1, le=500_000)
    candidate_limit: int = Field(default=500, ge=1, le=2_000)
    diversify_sources: bool = True
    require_text_match: bool = False
    preserve_evidence_order: bool = False

    @field_validator("consumer", "question", mode="before")
    @classmethod
    def strip_scalar_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "source_types",
        "source_asset_ids",
        "evidence_ids",
        "products",
        "regions",
        "user_segments",
        mode="before",
    )
    @classmethod
    def strip_list_text(cls, value: object) -> object:
        if isinstance(value, list):
            return [item.strip() if isinstance(item, str) else item for item in value]
        return value

    @field_validator(
        "statuses",
        "claim_types",
        "source_types",
        "source_asset_ids",
        "evidence_ids",
        "products",
        "regions",
        "user_segments",
    )
    @classmethod
    def values_are_unique(cls, value: list[object]) -> list[object]:
        normalized = [
            item.value if isinstance(item, StrEnum) else str(item).casefold()
            for item in value
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("evidence retrieval filters must be unique")
        return value

    @field_validator("statuses")
    @classmethod
    def only_agent_eligible_statuses(
        cls, value: list[EvidenceStatus]
    ) -> list[EvidenceStatus]:
        eligible = {
            EvidenceStatus.VERIFIED,
            EvidenceStatus.PARTIALLY_VERIFIED,
        }
        if set(value) - eligible:
            raise ValueError("shared retrieval only accepts agent-eligible Evidence")
        return value

    @model_validator(mode="after")
    def validate_limits_and_modes(self) -> "EvidenceRetrievalQuery":
        if self.candidate_limit < self.max_items:
            raise ValueError("candidate_limit must be greater than or equal to max_items")
        if self.preserve_evidence_order and not self.evidence_ids:
            raise ValueError("preserve_evidence_order requires evidence_ids")
        if self.preserve_evidence_order and self.candidate_limit < len(self.evidence_ids):
            raise ValueError(
                "candidate_limit must include every ordered evidence identifier"
            )
        if self.require_text_match and self.question is None:
            raise ValueError("require_text_match requires a question")
        return self


class EvidenceRetrievalMatch(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=80)
    rank: int = Field(ge=1)
    relevance_score: float = Field(ge=0, le=1)
    matched_terms: list[str] = Field(default_factory=list, max_length=100)
    match_reasons: list[str] = Field(default_factory=list, max_length=20)


class EvidenceRetrievalResult(StrictModel):
    consumer: str
    strategy: EvidenceRetrievalStrategy
    query_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_evidence_count: int = Field(ge=0)
    context: AgentEvidenceContext
    matches: list[EvidenceRetrievalMatch] = Field(default_factory=list)
