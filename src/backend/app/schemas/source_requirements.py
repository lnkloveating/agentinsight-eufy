"""项目资料范围和确定性准备度评估契约。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.evidence import EvidenceClaimType
from app.schemas.source_routing import SourceRouteTarget


class CompetitorResearchDimension(StrEnum):
    OFFICIAL_PRODUCT = "official_product"
    PRICE_CHANNEL = "price_channel"
    USER_REVIEW = "user_review"


class SourceReadinessStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class SourceRequirementStatus(StrEnum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    MISSING = "missing"
    BLOCKED = "blocked"


class SourceRequirementSeverity(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"


class ProductRole(StrEnum):
    TARGET = "target"
    COMPETITOR = "competitor"


class ProductReference(BaseModel):
    brand: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=160)
    variant: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("brand", "model", "variant", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def variant_requires_model(self) -> "ProductReference":
        if self.variant is not None and self.model is None:
            raise ValueError("product variant requires an exact model")
        return self


class SourceRequirementScopeUpdate(BaseModel):
    target_products: list[ProductReference] = Field(default_factory=list, max_length=20)
    competitors: list[ProductReference] = Field(default_factory=list, max_length=20)
    dimensions: list[CompetitorResearchDimension] = Field(
        default_factory=lambda: list(CompetitorResearchDimension),
        min_length=1,
        max_length=3,
    )
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("actor", "reason", mode="before")
    @classmethod
    def strip_audit_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("dimensions")
    @classmethod
    def unique_dimensions(
        cls, value: list[CompetitorResearchDimension]
    ) -> list[CompetitorResearchDimension]:
        if len(value) != len(set(value)):
            raise ValueError("source requirement dimensions must be unique")
        return value

    @model_validator(mode="after")
    def unique_products(self) -> "SourceRequirementScopeUpdate":
        for products in (self.target_products, self.competitors):
            identities = [_product_identity(item) for item in products]
            if len(identities) != len(set(identities)):
                raise ValueError("source requirement products must be unique within each role")
        overlap = set(map(_product_identity, self.target_products)) & set(
            map(_product_identity, self.competitors)
        )
        if overlap:
            raise ValueError("a product cannot be both target and competitor")
        return self


class SourceRequirementScope(BaseModel):
    target_products: list[ProductReference]
    competitors: list[ProductReference]
    dimensions: list[CompetitorResearchDimension]
    updated_by: str
    update_reason: str
    updated_at: datetime


class SourceRequirementItem(BaseModel):
    requirement_id: str
    requirement_key: str
    title: str
    severity: SourceRequirementSeverity
    status: SourceRequirementStatus
    product_role: ProductRole | None = None
    product: ProductReference | None = None
    dimension: CompetitorResearchDimension | None = None
    accepted_routes: list[SourceRouteTarget] = Field(default_factory=list)
    accepted_claim_types: list[EvidenceClaimType] = Field(default_factory=list)
    minimum_independent_sources: int = Field(default=0, ge=0)
    detected_source_asset_ids: list[str] = Field(default_factory=list)
    matched_source_asset_ids: list[str] = Field(default_factory=list)
    matched_evidence_ids: list[str] = Field(default_factory=list)
    reason: str
    recommended_actions: list[str] = Field(default_factory=list)


class SourceRequirementAssessment(BaseModel):
    project_id: str
    status: SourceReadinessStatus
    region: str
    scope: SourceRequirementScope | None
    requirements: list[SourceRequirementItem]
    required_count: int = Field(ge=0)
    satisfied_required_count: int = Field(ge=0)
    missing_required_count: int = Field(ge=0)
    unassigned_source_asset_ids: list[str] = Field(default_factory=list)
    missing_actions: list[str] = Field(default_factory=list)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime


def _product_identity(product: ProductReference) -> tuple[str, str, str]:
    return (
        product.brand.casefold(),
        (product.model or "").casefold(),
        (product.variant or "").casefold(),
    )
