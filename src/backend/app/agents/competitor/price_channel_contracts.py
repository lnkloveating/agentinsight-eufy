"""价格渠道专家的强类型模型输出与确定性最终 Payload。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriceKind(StrEnum):
    REGULAR = "regular"
    SALE = "sale"
    MEMBER = "member"
    BUNDLE = "bundle"
    FROM = "from"


class ChannelAvailabilityStatus(StrEnum):
    LISTED = "listed"
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class PriceGapSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CitedPriceItem(StrictModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=30)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class PriceObservationDraft(CitedPriceItem):
    observation_id: str = Field(min_length=1, max_length=80)
    scope_label: str = Field(min_length=1, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    price_kind: PriceKind
    region: str = Field(min_length=1, max_length=120)
    channel_name: str = Field(min_length=1, max_length=240)
    seller_name: str | None = Field(default=None, max_length=240)
    variant: str | None = Field(default=None, max_length=500)
    promotion_terms: str | None = Field(default=None, max_length=1_500)
    confidence: float = Field(ge=0, le=1)


class ChannelObservationDraft(CitedPriceItem):
    observation_id: str = Field(min_length=1, max_length=80)
    scope_label: str = Field(min_length=1, max_length=240)
    channel_name: str = Field(min_length=1, max_length=240)
    seller_name: str | None = Field(default=None, max_length=240)
    region: str = Field(min_length=1, max_length=120)
    availability: ChannelAvailabilityStatus
    variant: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)


class PriceContradiction(CitedPriceItem):
    statement: str = Field(min_length=1, max_length=2_000)


class PriceResearchGap(StrictModel):
    scope_label: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    severity: PriceGapSeverity
    recommended_source_types: list[str] = Field(default_factory=list, max_length=20)


class PriceChannelModelOutput(StrictModel):
    """模型只提取语义；观察时间与质量状态由后端生成。"""

    summary: str = Field(min_length=1, max_length=4_000)
    summary_evidence_ids: list[str] = Field(min_length=1, max_length=30)
    price_observations: list[PriceObservationDraft] = Field(default_factory=list, max_length=200)
    channel_observations: list[ChannelObservationDraft] = Field(
        default_factory=list, max_length=200
    )
    contradictions: list[PriceContradiction] = Field(default_factory=list, max_length=50)
    research_gaps: list[PriceResearchGap] = Field(default_factory=list, max_length=50)
    unknowns: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> PriceChannelModelOutput:
        if len(self.summary_evidence_ids) != len(set(self.summary_evidence_ids)):
            raise ValueError("summary_evidence_ids must be unique")
        identifiers = [
            *(item.observation_id for item in self.price_observations),
            *(item.observation_id for item in self.channel_observations),
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("observation_id must be unique across the output")
        return self

    def cited_evidence_ids(self) -> set[str]:
        citations = set(self.summary_evidence_ids)
        for item in [*self.price_observations, *self.channel_observations]:
            citations.update(item.evidence_ids)
        for contradiction in self.contradictions:
            citations.update(contradiction.evidence_ids)
        return citations


class PriceObservation(PriceObservationDraft):
    observed_from: datetime
    observed_to: datetime


class ChannelObservation(ChannelObservationDraft):
    observed_from: datetime
    observed_to: datetime


class PriceChannelEvidenceCoverage(StrictModel):
    requested_product_count: int = Field(ge=0)
    price_product_count: int = Field(ge=0)
    channel_product_count: int = Field(ge=0)
    available_evidence_count: int = Field(ge=0)
    included_evidence_count: int = Field(ge=0)
    cited_evidence_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    price_observation_count: int = Field(ge=0)
    channel_observation_count: int = Field(ge=0)
    time_bounded_observation_count: int = Field(ge=0)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class PriceChannelPayload(StrictModel):
    schema_name: str = "price_channel_intelligence"
    schema_version: str = "1.0"
    summary: str
    summary_evidence_ids: list[str]
    price_observations: list[PriceObservation]
    channel_observations: list[ChannelObservation]
    contradictions: list[PriceContradiction]
    research_gaps: list[PriceResearchGap]
    evidence_coverage: PriceChannelEvidenceCoverage
