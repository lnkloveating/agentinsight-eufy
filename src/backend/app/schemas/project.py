from datetime import datetime
from enum import StrEnum
from typing import Any

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


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_REVISION = "needs_revision"
    CANCELLED = "cancelled"


class DecisionAction(StrEnum):
    APPROVE = "approve"
    REVISE = "revise"
    RESEARCH_MORE = "research_more"
    REJECT = "reject"
    TERMINATE = "terminate"


class ResearchBrief(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    category: str = Field(min_length=1, max_length=120)
    target_user: str = Field(min_length=1, max_length=240)
    region: str = Field(min_length=1, max_length=120)
    scenarios: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    focus_dimensions: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    brief: ResearchBrief


class PendingDecision(BaseModel):
    decision_id: str
    gate: str
    allowed_actions: list[DecisionAction]


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
    action: DecisionAction
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(min_length=1, max_length=120)
    selected_concept_ids: list[str] = Field(default_factory=list)


class AgentRun(BaseModel):
    agent_run_id: str
    project_id: str
    task_id: str | None = None
    agent_type: str
    agent_name: str
    status: AgentRunStatus
    progress: int = Field(ge=0, le=100)
    quality_score: float = Field(default=0, ge=0, le=100)
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class ProjectEvent(BaseModel):
    event_id: str
    event_type: str
    project_id: str
    sequence_number: int = Field(ge=1)
    timestamp: datetime
    data: dict[str, Any]
    trace_id: str
