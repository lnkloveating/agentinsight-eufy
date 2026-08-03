from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_BRIEF_APPROVAL = "awaiting_brief_approval"
    RESEARCHING = "researching"
    AWAITING_CONCEPT_APPROVAL = "awaiting_concept_approval"
    SUPPLEMENTING_RESEARCH = "supplementing_research"
    GENERATING_REPORT = "generating_report"
    AWAITING_FINAL_APPROVAL = "awaiting_final_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class ResearchBrief(BaseModel):
    question: str
    category: str
    target_user: str
    region: str
    scenarios: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    focus_dimensions: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    brief: ResearchBrief


class PendingDecision(BaseModel):
    decision_id: str
    gate: str
    allowed_actions: list[str]


class Project(BaseModel):
    project_id: str
    status: ProjectStatus
    current_stage: str
    progress: int = Field(ge=0, le=100)
    brief: ResearchBrief
    pending_decision: PendingDecision | None = None
    created_at: datetime
    updated_at: datetime


class DecisionCreate(BaseModel):
    decision_id: str
    action: str
    reason: str
    actor: str
    selected_concept_ids: list[str] = Field(default_factory=list)
