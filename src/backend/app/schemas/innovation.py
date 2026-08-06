"""未来产品候选、事件理解、评分和红队公开契约。"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class InnovationStatus(StrEnum):
    DRAFT = "draft"
    EVIDENCE_PENDING = "evidence_pending"
    TECH_REVIEW = "tech_review"
    BUSINESS_REVIEW = "business_review"
    RED_TEAM_REVIEW = "red_team_review"
    NEEDS_REVISION = "needs_revision"
    RECOMMENDED = "recommended"
    REJECTED = "rejected"


class SignalAvailability(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"
    UNVERIFIED = "unverified"


class RedTeamSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RedTeamDecision(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    RESEARCH_MORE = "research_more"
    REJECT = "reject"


class ScoreDimension(StrEnum):
    USER_PAIN = "user_pain"
    FREQUENCY = "frequency"
    EVIDENCE_STRENGTH = "evidence_strength"
    COMPETITOR_DIFFERENTIATION = "competitor_differentiation"
    EVENT_UNDERSTANDING = "event_understanding"
    TECHNICAL_DATA_FEASIBILITY = "technical_data_feasibility"
    BUSINESS_VALUE = "business_value"
    DEMO_FEASIBILITY = "demo_feasibility"


class EventReference(BaseModel):
    type: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=160)


class ContextSignal(BaseModel):
    type: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=160)
    availability: SignalAvailability
    authorization: str = Field(min_length=1, max_length=500)
    freshness: str = Field(min_length=1, max_length=160)
    latency_ms: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    fallback: str = Field(min_length=1, max_length=1000)


class EventUnderstanding(BaseModel):
    base_event: EventReference
    event_state: EventReference
    context_signals: list[ContextSignal] = Field(min_length=2)
    inference: str = Field(min_length=1)
    risk_or_value: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)


class TargetUser(BaseModel):
    persona_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)


class ProblemDefinition(BaseModel):
    pain_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)


class ScoreComponent(BaseModel):
    score: float = Field(ge=0, le=100)
    weight: float = Field(gt=0, le=1)
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class RedTeamReview(BaseModel):
    severity: RedTeamSeverity
    critical_assumptions: list[str] = Field(default_factory=list)
    evidence_issues: list[str] = Field(default_factory=list)
    event_understanding_challenges: list[str] = Field(default_factory=list)
    competitor_challenges: list[str] = Field(default_factory=list)
    technical_risks: list[str] = Field(default_factory=list)
    business_risks: list[str] = Field(default_factory=list)
    privacy_and_safety_risks: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    score_adjustments: dict[ScoreDimension, float] = Field(default_factory=dict)
    decision: RedTeamDecision

    @model_validator(mode="after")
    def high_severity_cannot_silently_pass(self) -> "RedTeamReview":
        if self.severity is RedTeamSeverity.HIGH and self.decision is RedTeamDecision.PASS:
            raise ValueError("A high-severity red-team review cannot pass")
        if any(adjustment > 0 for adjustment in self.score_adjustments.values()):
            raise ValueError("Red-team score adjustments cannot increase a score")
        return self


class InnovationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    target_user: TargetUser
    problem: ProblemDefinition
    event_understanding: EventUnderstanding
    competitor_gap_ids: list[str] = Field(default_factory=list)
    technical_assessment: dict[str, Any] = Field(default_factory=dict)
    business_assessment: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(min_length=1)


class InnovationScoreInput(BaseModel):
    score_breakdown: dict[ScoreDimension, ScoreComponent]


class Innovation(BaseModel):
    innovation_id: str
    name: str
    status: InnovationStatus
    target_user: TargetUser
    problem: ProblemDefinition
    event_understanding: EventUnderstanding
    competitor_gap_ids: list[str]
    technical_assessment: dict[str, Any] = Field(default_factory=dict)
    business_assessment: dict[str, Any] = Field(default_factory=dict)
    red_team_review: RedTeamReview | None = None
    evidence_ids: list[str] = Field(min_length=1)
    score_breakdown: dict[ScoreDimension, ScoreComponent] = Field(default_factory=dict)
    final_score: float = Field(ge=0, le=100)


class InnovationRecord(Innovation):
    """工作流内部可见、公开 API 不直接暴露的门禁审计字段。"""

    base_score: float = Field(ge=0, le=100)
    gate_issues: list[str] = Field(default_factory=list)


class InnovationPortfolioGateResult(BaseModel):
    candidate_count: int = Field(ge=0)
    minimum_candidates: int = Field(ge=1)
    ready_for_scenario_approval: bool
    gaps: list[str] = Field(default_factory=list)
