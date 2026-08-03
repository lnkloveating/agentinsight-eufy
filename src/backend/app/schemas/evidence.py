from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class Evidence(BaseModel):
    evidence_id: str
    source_url: HttpUrl
    source_type: str
    title: str
    excerpt: str
    captured_at: datetime
    status: str
    content_hash: str
    confidence: float = Field(ge=0, le=1)


class EvidencePage(BaseModel):
    items: list[Evidence]
    next_cursor: str | None = None
    total: int = Field(ge=0)


class Claim(BaseModel):
    claim_id: str
    statement: str
    evidence_ids: list[str]
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    status: str
