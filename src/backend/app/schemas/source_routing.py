"""统一资料中心的多标签路由契约。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.evidence import EvidenceClaimType


class SourceRouteTarget(StrEnum):
    OFFICIAL_PRODUCT = "official_product"
    PRICE_CHANNEL = "price_channel"
    USER_REVIEW = "user_review"
    USER_RESEARCH = "user_research"
    MARKET_RESEARCH = "market_research"
    TECHNICAL_DOCUMENT = "technical_document"
    COMMERCIAL_DATA = "commercial_data"
    ENTERPRISE_INTERNAL = "enterprise_internal"
    MEDIA_REVIEW = "media_review"


class SourceRoutingStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SourceRoutingMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL = "model"
    HYBRID = "hybrid"
    MANUAL = "manual"


class SourceRoutingSuggestedBy(StrEnum):
    RULE = "rule"
    MODEL = "model"
    HYBRID = "hybrid"
    USER = "user"


class SourceRoutingSuggestion(BaseModel):
    route: SourceRouteTarget
    claim_types: list[EvidenceClaimType] = Field(min_length=1, max_length=20)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1000)
    signals: list[str] = Field(default_factory=list, max_length=30)
    suggested_by: SourceRoutingSuggestedBy

    @field_validator("claim_types", "signals")
    @classmethod
    def unique_values(cls, value: list[object]) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError("routing suggestion values must be unique")
        return value


class SourceRoutingModelOutput(BaseModel):
    suggestions: list[SourceRoutingSuggestion] = Field(default_factory=list, max_length=12)
    unknowns: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_routes(self) -> "SourceRoutingModelOutput":
        routes = [item.route for item in self.suggestions]
        if len(routes) != len(set(routes)):
            raise ValueError("source routing suggestions must use unique routes")
        if any(
            item.suggested_by is not SourceRoutingSuggestedBy.MODEL for item in self.suggestions
        ):
            raise ValueError("model output suggestions must be marked as model")
        return self


class SourceRoutingAnalyze(BaseModel):
    use_model: bool = True
    force: bool = False


class SourceRoutingSelection(BaseModel):
    route: SourceRouteTarget
    claim_types: list[EvidenceClaimType] = Field(min_length=1, max_length=20)

    @field_validator("claim_types")
    @classmethod
    def unique_claim_types(cls, value: list[EvidenceClaimType]) -> list[EvidenceClaimType]:
        if len(value) != len(set(value)):
            raise ValueError("routing selection claim types must be unique")
        return value


class SourceRoutingDecisionAction(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"


class SourceRoutingDecision(BaseModel):
    action: SourceRoutingDecisionAction
    selections: list[SourceRoutingSelection] = Field(default_factory=list, max_length=12)
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_action(self) -> "SourceRoutingDecision":
        routes = [item.route for item in self.selections]
        if len(routes) != len(set(routes)):
            raise ValueError("routing decision routes must be unique")
        if self.action is SourceRoutingDecisionAction.CONFIRM and not self.selections:
            raise ValueError("confirmed routing requires at least one selection")
        if self.action is SourceRoutingDecisionAction.REJECT and self.selections:
            raise ValueError("rejected routing cannot include selections")
        return self


class SourceRouting(BaseModel):
    source_routing_id: str
    project_id: str
    source_asset_id: str
    status: SourceRoutingStatus
    method: SourceRoutingMethod
    suggestions: list[SourceRoutingSuggestion]
    confirmed_routes: list[SourceRouteTarget]
    confirmed_claim_types: list[EvidenceClaimType]
    rule_signals: list[str]
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_id: str | None = None
    model_call_id: str | None = None
    analyzed_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    updated_at: datetime
