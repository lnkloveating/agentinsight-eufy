"""竞品研究 A2A 子任务的稳定契约。

本模块只描述任务、证据请求和专家交付物，不包含任何业务 Prompt 或竞品事实。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from app.application.runtime import CancellationToken
from app.workflows.contracts import AgentContext, ResearchTaskStatus


class CompetitorSpecialistType(StrEnum):
    OFFICIAL_PRODUCT = "official_product"
    PRICE_CHANNEL = "price_channel"
    USER_REVIEW = "user_review"


class A2ATaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class A2AErrorCode(StrEnum):
    SPECIALIST_NOT_BOUND = "specialist_not_bound"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ADAPTER_FAILED = "adapter_failed"
    ARTIFACT_INVALID = "artifact_invalid"


class EvidenceRequest(BaseModel):
    """主管交给专家的数据需求；它是检索任务，不是事实结论。"""

    request_id: str = Field(min_length=1, max_length=80)
    project_id: str = Field(min_length=1, max_length=80)
    parent_task_id: str = Field(min_length=1, max_length=80)
    specialist_type: CompetitorSpecialistType
    research_questions: list[str] = Field(min_length=1, max_length=20)
    product_scope: list[str] = Field(default_factory=list, max_length=50)
    region: str | None = Field(default=None, max_length=120)
    evidence_types: list[str] = Field(min_length=1, max_length=20)
    allowed_claim_types: list[str] = Field(min_length=1, max_length=20)
    minimum_independent_domains: int = Field(default=2, ge=1, le=20)
    max_evidence_items: int = Field(default=30, ge=1, le=200)

    @model_validator(mode="after")
    def reject_duplicate_inputs(self) -> EvidenceRequest:
        for values, field_name in (
            (self.research_questions, "research_questions"),
            (self.product_scope, "product_scope"),
            (self.evidence_types, "evidence_types"),
            (self.allowed_claim_types, "allowed_claim_types"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} cannot contain duplicates")
        return self


class CompetitorFinding(BaseModel):
    """一个可被下游引用的事实性发现，必须携带 Evidence ID。"""

    finding_id: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[str] = Field(min_length=1, max_length=50)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def reject_duplicate_evidence(self) -> CompetitorFinding:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("finding evidence_ids cannot contain duplicates")
        return self


class CompetitorSpecialistArtifact(BaseModel):
    """一个专家的结构化输出；主管只能聚合，不能补写没有证据的事实。"""

    a2a_task_id: str = Field(min_length=1, max_length=80)
    request_id: str = Field(min_length=1, max_length=80)
    specialist_type: CompetitorSpecialistType
    status: ResearchTaskStatus
    findings: list[CompetitorFinding] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_terminal_artifact(self) -> CompetitorSpecialistArtifact:
        allowed = {
            ResearchTaskStatus.COMPLETED,
            ResearchTaskStatus.PARTIAL,
            ResearchTaskStatus.BLOCKED,
        }
        if self.status not in allowed:
            raise ValueError("specialist artifact must use a supported terminal status")
        cited = {evidence_id for finding in self.findings for evidence_id in finding.evidence_ids}
        if not cited.issubset(set(self.evidence_ids)):
            raise ValueError("finding evidence_ids must be included in artifact evidence_ids")
        if self.status is ResearchTaskStatus.COMPLETED and not self.findings:
            raise ValueError("completed specialist artifact must contain findings")
        if self.status is ResearchTaskStatus.COMPLETED and not self.evidence_ids:
            raise ValueError("completed specialist artifact must cite evidence")
        return self


@dataclass(frozen=True)
class A2ASpecialistInvocation:
    a2a_task_id: str
    parent_agent_run_id: str
    trace_id: str
    attempt_number: int
    request: EvidenceRequest
    context: AgentContext
    cancellation_token: CancellationToken


class A2ASpecialistAdapter(Protocol):
    @property
    def adapter_type(self) -> str: ...

    async def execute(self, invocation: A2ASpecialistInvocation) -> object: ...


class A2AGatewayError(RuntimeError):
    def __init__(
        self,
        code: A2AErrorCode,
        message: str,
        *,
        a2a_task_id: str,
        specialist_type: CompetitorSpecialistType,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.a2a_task_id = a2a_task_id
        self.specialist_type = specialist_type
        self.retryable = retryable
        self.details = details or {}
        super().__init__(message)


class CompetitorA2ABatchError(RuntimeError):
    """至少一个已绑定专家失败；重试时会复用其他专家的成功结果。"""

    def __init__(self, failures: list[A2AGatewayError]) -> None:
        self.failures = tuple(failures)
        super().__init__("one or more competitor A2A specialist tasks failed")


class SpecialistTaskResult(BaseModel):
    a2a_task_id: str
    request: EvidenceRequest
    status: A2ATaskStatus
    artifact: CompetitorSpecialistArtifact | None = None
    reused: bool = False
    attempt_number: int = Field(ge=0)
    error_code: A2AErrorCode | None = None
    error_message: str | None = None
