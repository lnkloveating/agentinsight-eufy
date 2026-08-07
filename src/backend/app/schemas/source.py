from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SourceAssetKind(StrEnum):
    FILE = "file"
    LINK = "link"


class SourceAssetStatus(StrEnum):
    READY = "ready"
    DELETED = "deleted"


class SourceMediaCategory(StrEnum):
    DOCUMENT = "document"
    DATASET = "dataset"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    WEBPAGE = "webpage"


class SourceAuthorizationBasis(StrEnum):
    USER_OWNED = "user_owned"
    ENTERPRISE_AUTHORIZED = "enterprise_authorized"
    PUBLICLY_AVAILABLE = "publicly_available"


class SourceFileMetadata(BaseModel):
    authorization_basis: SourceAuthorizationBasis
    authorization_confirmed: bool
    authorized_by: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)


class SourceLinkCreate(BaseModel):
    source_url: HttpUrl
    display_name: str = Field(min_length=1, max_length=255)
    authorization_basis: SourceAuthorizationBasis
    authorization_confirmed: Literal[True]
    authorized_by: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)


class SourceAsset(BaseModel):
    source_asset_id: str
    project_id: str
    kind: SourceAssetKind
    status: SourceAssetStatus
    display_name: str
    original_filename: str | None = None
    source_url: HttpUrl | None = None
    media_type: str
    media_category: SourceMediaCategory
    content_hash: str
    byte_size: int = Field(ge=0)
    authorization_basis: SourceAuthorizationBasis
    authorization_confirmed_at: datetime
    authorized_by: str
    purpose: str
    collection_job_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class SourceAssetIngestResult(BaseModel):
    source_asset: SourceAsset
    created: bool


class SourceAssetPage(BaseModel):
    items: list[SourceAsset]
    next_cursor: str | None = None
    total: int = Field(ge=0)
