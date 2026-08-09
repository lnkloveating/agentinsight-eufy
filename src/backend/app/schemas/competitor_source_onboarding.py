"""已确认竞品候选到授权 Source Asset 的批量接入契约。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.source import SourceAsset, SourceAuthorizationBasis
from app.schemas.source_requirements import ProductReference


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompetitorSourceOnboardingCreate(StrictModel):
    artifact_id: str = Field(min_length=1, max_length=80)
    authorization_basis: Literal[SourceAuthorizationBasis.PUBLICLY_AVAILABLE]
    authorization_confirmed: Literal[True]
    authorized_by: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=300)

    @field_validator("artifact_id", "authorized_by", "purpose", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CompetitorSourceOnboardingItem(StrictModel):
    onboarding_item_id: str
    proposal_id: str
    candidate_id: str
    product: ProductReference
    source_asset: SourceAsset
    source_asset_created: bool


class CompetitorSourceOnboarding(StrictModel):
    onboarding_id: str
    project_id: str
    artifact_id: str
    decision_id: str
    status: Literal["completed"] = "completed"
    authorization_basis: Literal[SourceAuthorizationBasis.PUBLICLY_AVAILABLE]
    authorized_by: str
    purpose: str
    total_item_count: int = Field(ge=1)
    unique_source_asset_count: int = Field(ge=1)
    created_source_asset_count: int = Field(ge=0)
    reused_source_asset_count: int = Field(ge=0)
    items: list[CompetitorSourceOnboardingItem] = Field(min_length=1)
    created_at: datetime


class CompetitorSourceOnboardingResult(StrictModel):
    onboarding: CompetitorSourceOnboarding
    created: bool


class CompetitorSourceOnboardingPage(StrictModel):
    items: list[CompetitorSourceOnboarding]
    total: int = Field(ge=0)
