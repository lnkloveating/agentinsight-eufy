"""竞品资料发现、人工确认与来源血缘契约。"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.search_discovery import SearchDiscoveryCandidate, SearchDiscoveryRun
from app.schemas.source import SourceAsset, SourceAuthorizationBasis
from app.schemas.source_requirements import (
    CompetitorResearchDimension,
    ProductReference,
    ProductRole,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompetitorMaterialDiscoveryStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class CompetitorMaterialDecisionAction(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"


class CompetitorMaterialProductSelection(StrictModel):
    product_role: ProductRole
    product: ProductReference


class CompetitorMaterialDiscoveryCreate(StrictModel):
    products: list[CompetitorMaterialProductSelection] = Field(
        default_factory=list, max_length=6
    )
    dimensions: list[CompetitorResearchDimension] = Field(
        default_factory=list, max_length=3
    )
    provider_id: str = Field(default="tavily", min_length=1, max_length=80)
    max_results_per_query: int = Field(default=5, ge=1, le=10)
    requested_by: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)

    @field_validator("provider_id", mode="before")
    @classmethod
    def normalize_provider_id(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("requested_by", "purpose", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def selections_are_unique(self) -> "CompetitorMaterialDiscoveryCreate":
        product_keys = [
            (
                item.product_role.value,
                item.product.brand.strip().casefold(),
                (item.product.model or "").strip().casefold(),
                (item.product.variant or "").strip().casefold(),
            )
            for item in self.products
        ]
        if len(product_keys) != len(set(product_keys)):
            raise ValueError("competitor material products must be unique")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("competitor material dimensions must be unique")
        return self


class CompetitorMaterialDiscoveryItem(StrictModel):
    material_discovery_item_id: str
    product_role: ProductRole
    product: ProductReference
    dimension: CompetitorResearchDimension
    query: str
    search_run: SearchDiscoveryRun


class CompetitorMaterialSelection(StrictModel):
    material_selection_id: str
    material_discovery_item_id: str
    search_discovery_run_id: str
    candidate_id: str
    product_role: ProductRole
    product: ProductReference
    dimension: CompetitorResearchDimension
    candidate: SearchDiscoveryCandidate
    source_asset: SourceAsset
    source_asset_created: bool


class CompetitorMaterialDecisionCreate(StrictModel):
    action: CompetitorMaterialDecisionAction
    selected_candidate_ids: list[str] = Field(default_factory=list, max_length=60)
    authorization_basis: Literal[SourceAuthorizationBasis.PUBLICLY_AVAILABLE] | None = None
    authorization_confirmed: bool = False
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1_000)

    @field_validator("actor", "reason", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("selected_candidate_ids")
    @classmethod
    def candidate_ids_are_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("selected candidate IDs must be non-empty and unique")
        return normalized

    @model_validator(mode="after")
    def validate_gate(self) -> "CompetitorMaterialDecisionCreate":
        if self.action is CompetitorMaterialDecisionAction.CONFIRM:
            if not self.selected_candidate_ids:
                raise ValueError("confirm requires selected candidate IDs")
            if (
                self.authorization_basis
                is not SourceAuthorizationBasis.PUBLICLY_AVAILABLE
                or not self.authorization_confirmed
            ):
                raise ValueError("confirm requires explicit public-source authorization")
        elif self.selected_candidate_ids or self.authorization_basis is not None:
            raise ValueError("reject must not select or authorize candidates")
        return self


class CompetitorMaterialDecision(StrictModel):
    material_decision_id: str
    project_id: str
    material_discovery_id: str
    action: CompetitorMaterialDecisionAction
    selected_candidate_ids: list[str]
    authorization_basis: Literal[SourceAuthorizationBasis.PUBLICLY_AVAILABLE] | None
    authorization_confirmed: bool
    actor: str
    reason: str
    selections: list[CompetitorMaterialSelection]
    created_at: datetime


class CompetitorMaterialDiscovery(StrictModel):
    material_discovery_id: str
    project_id: str
    status: CompetitorMaterialDiscoveryStatus
    provider_id: str
    max_results_per_query: int = Field(ge=1, le=10)
    products: list[CompetitorMaterialProductSelection]
    dimensions: list[CompetitorResearchDimension]
    scope_hash: str
    item_count: int = Field(ge=1, le=18)
    completed_item_count: int = Field(ge=0, le=18)
    candidate_count: int = Field(ge=0)
    items: list[CompetitorMaterialDiscoveryItem]
    decision: CompetitorMaterialDecision | None
    requested_by: str
    purpose: str
    created_at: datetime
    completed_at: datetime | None


class CompetitorMaterialDiscoveryPage(StrictModel):
    items: list[CompetitorMaterialDiscovery]
    total: int = Field(ge=0)


class CompetitorMaterialDecisionResult(StrictModel):
    decision: CompetitorMaterialDecision
    created: bool
