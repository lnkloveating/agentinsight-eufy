"""LangGraph 主图使用的结构化任务、产物、门禁和状态契约。"""

from __future__ import annotations

import operator
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field, model_validator

from app.schemas.project import DecisionAction, ResearchBrief


class ResearchAgentType(StrEnum):
    RESEARCH_MANAGER = "research_manager"
    USER_RESEARCH = "user_research"
    COMPETITOR_RESEARCH = "competitor_research"
    PRODUCT_TECHNICAL = "product_technical"
    COMMERCIAL_EVALUATION = "commercial_evaluation"
    RED_TEAM = "red_team"
    CANDIDATE_SYNTHESIS = "candidate_synthesis"
    VALIDATION = "validation"
    FINAL_SYNTHESIS = "final_synthesis"


class ResearchTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_REVISION = "needs_revision"
    CANCELLED = "cancelled"


class GateName(StrEnum):
    BRIEF = "brief"
    SCENARIO = "scenario"
    FINAL = "final"


class WorkflowOutcome(StrEnum):
    RUNNING = "running"
    AWAITING_DECISION = "awaiting_decision"
    COMPLETED = "completed"
    REJECTED = "rejected"
    TERMINATED = "terminated"
    INCONCLUSIVE = "inconclusive"


class EvidenceRules(BaseModel):
    citation_required: bool = True
    minimum_independent_domains: int = Field(default=2, ge=1, le=20)


class ResearchBudget(BaseModel):
    max_pages: int = Field(default=50, ge=0, le=1000)
    max_iterations: int = Field(default=2, ge=0, le=10)
    deadline_seconds: int = Field(default=600, ge=1, le=86400)


class ResearchTask(BaseModel):
    task_id: str = Field(min_length=1, max_length=80)
    project_id: str = Field(min_length=1, max_length=80)
    agent_type: ResearchAgentType
    goal: str = Field(min_length=1, max_length=2000)
    scope: dict[str, Any] = Field(default_factory=dict)
    required_artifacts: list[str] = Field(default_factory=list)
    evidence_rules: EvidenceRules = Field(default_factory=EvidenceRules)
    budget: ResearchBudget = Field(default_factory=ResearchBudget)
    depends_on: list[str] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)


class ResearchArtifact(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=80)
    task_id: str = Field(min_length=1, max_length=80)
    artifact_type: str = Field(min_length=1, max_length=120)
    schema_version: str = Field(default="1.0", min_length=1, max_length=20)
    status: ResearchTaskStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0, le=100)
    errors: list[str] = Field(default_factory=list)


class AgentEvidence(BaseModel):
    """提供给 Agent 的证据投影；只包含可引用原文与必要来源元数据。"""

    evidence_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    original_excerpt: str = Field(min_length=1, max_length=10_000)
    claim_type: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=80)
    source_type: str = Field(min_length=1, max_length=80)
    source_url: str | None = Field(default=None, max_length=2000)
    source_domain: str | None = Field(default=None, max_length=253)
    source_asset_id: str | None = Field(default=None, max_length=80)
    source_fragment_id: str | None = Field(default=None, max_length=80)
    source_locator: dict[str, Any] | None = None
    product: str | None = Field(default=None, max_length=160)
    region: str | None = Field(default=None, max_length=120)
    user_segment: str | None = Field(default=None, max_length=160)
    published_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    authority_score: float = Field(ge=0, le=1)
    recency_score: float = Field(ge=0, le=1)
    diversity_score: float = Field(ge=0, le=1)


class AgentEvidenceContext(BaseModel):
    """记录确定性筛选后的输入边界，供所有领域 Agent 复用。"""

    items: list[AgentEvidence] = Field(default_factory=list)
    available_evidence_count: int = Field(ge=0)
    included_evidence_count: int = Field(ge=0)
    omitted_evidence_count: int = Field(ge=0)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentContext(BaseModel):
    """传给单个 Agent 的最小必要上下文，不包含隐藏思维或完整网页。"""

    project_id: str
    brief: ResearchBrief
    iteration: int = Field(ge=0)
    upstream_artifacts: dict[str, ResearchArtifact] = Field(default_factory=dict)
    selected_innovation_ids: list[str] = Field(default_factory=list)
    decision_history: list[StageDecision] = Field(default_factory=list)
    evidence_context: AgentEvidenceContext | None = None


class StageDecision(BaseModel):
    decision_id: str = Field(min_length=1, max_length=80)
    gate: GateName
    action: DecisionAction
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)
    selected_innovation_ids: list[str] = Field(default_factory=list)
    affected_task_ids: list[str] = Field(default_factory=list)
    resume_checkpoint_id: str | None = Field(default=None, max_length=120)


class GateRequest(BaseModel):
    decision_id: str
    gate: GateName
    allowed_actions: list[DecisionAction]
    project_id: str
    checkpoint_hint: str
    summary: dict[str, Any] = Field(default_factory=dict)


class EvidenceGateResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)


class RedTeamDirective(BaseModel):
    decision: str
    severity: str
    affected_task_ids: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_high_severity_pass(self) -> RedTeamDirective:
        if self.severity == "high" and self.decision == "pass":
            raise ValueError("high severity red-team findings cannot pass")
        if self.decision not in {"pass", "revise", "research_more", "reject"}:
            raise ValueError("unsupported red-team decision")
        return self


class WorkflowEvent(BaseModel):
    event_type: str
    node: str
    task_id: str | None = None
    status: str
    message: str


def merge_artifacts(
    left: dict[str, dict[str, Any]],
    right: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """让并行节点只合并各自的结构化 Artifact。"""

    return {**left, **right}


class ResearchState(TypedDict, total=False):
    project_id: str
    brief: dict[str, Any]
    outcome: str
    current_stage: str
    progress: int
    task_plan: list[dict[str, Any]]
    artifacts: Annotated[dict[str, dict[str, Any]], merge_artifacts]
    evidence_gate: dict[str, Any]
    routing_decision: str
    iteration: int
    max_iterations: int
    affected_task_ids: list[str]
    selected_innovation_ids: list[str]
    pending_gate: dict[str, Any] | None
    decision_history: Annotated[list[dict[str, Any]], operator.add]
    node_history: Annotated[list[dict[str, Any]], operator.add]
    terminal_reason: str | None


class WorkflowContractError(ValueError):
    """结构化 Agent 输出或人工决定违反工作流契约。"""


class WorkflowNodeError(RuntimeError):
    """保留失败节点和任务信息，交由 Checkpoint 恢复同一 superstep。"""

    def __init__(self, node: str, task_id: str, cause: Exception) -> None:
        self.node = node
        self.task_id = task_id
        self.cause = cause
        super().__init__(f"workflow node {node} failed for {task_id}: {cause}")
