from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Report(BaseModel):
    report_id: str
    project_id: str
    version: int = Field(ge=1)
    recommendation: str
    sections: dict[str, Any]
    cited_evidence_ids: list[str]
    unknowns: list[str] = Field(default_factory=list)
    generated_at: datetime


class Metrics(BaseModel):
    elapsed_seconds: float = Field(ge=0)
    valid_evidence_count: int = Field(ge=0)
    citation_coverage: float = Field(ge=0, le=1)
    source_diversity: int = Field(ge=0)
    estimated_cost: float = Field(ge=0)
    comparison: dict[str, Any] = Field(default_factory=dict)
