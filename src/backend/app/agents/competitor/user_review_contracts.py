"""竞品用户评价专家的模型输出与确定性最终 Payload。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewSentiment(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"


class ReviewGapSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewRecurrenceStatus(StrEnum):
    SINGLE_REPORT = "single_report"
    REPEATED_ACROSS_SOURCES = "repeated_across_sources"


class CitedReviewItem(StrictModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=50)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class ReviewThemeDraft(CitedReviewItem):
    theme_id: str = Field(min_length=1, max_length=80)
    scope_label: str = Field(min_length=1, max_length=240)
    theme: str = Field(min_length=1, max_length=500)
    sentiment: ReviewSentiment
    user_expression: str = Field(min_length=1, max_length=2_000)
    event_context: str = Field(min_length=1, max_length=1_500)
    user_impact: str = Field(min_length=1, max_length=1_500)
    user_segment: str | None = Field(default=None, max_length=240)
    region: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0, le=1)


class ReviewTheme(ReviewThemeDraft):
    support_count: int = Field(ge=1)
    independent_source_count: int = Field(ge=1)
    recurrence_status: ReviewRecurrenceStatus


class ReviewContradiction(CitedReviewItem):
    scope_label: str = Field(min_length=1, max_length=240)
    statement: str = Field(min_length=1, max_length=2_000)


class ReviewSampleLimitation(CitedReviewItem):
    scope_label: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=1_500)
    impact: str = Field(min_length=1, max_length=1_500)


class ReviewResearchGap(StrictModel):
    scope_label: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    severity: ReviewGapSeverity
    recommended_source_types: list[str] = Field(default_factory=list, max_length=20)


class CompetitorUserReviewModelOutput(StrictModel):
    """模型负责归纳语义；重复性、覆盖率和状态由后端计算。"""

    summary: str = Field(min_length=1, max_length=4_000)
    summary_evidence_ids: list[str] = Field(min_length=1, max_length=50)
    review_themes: list[ReviewThemeDraft] = Field(default_factory=list, max_length=200)
    contradictions: list[ReviewContradiction] = Field(default_factory=list, max_length=50)
    sample_limitations: list[ReviewSampleLimitation] = Field(default_factory=list, max_length=50)
    research_gaps: list[ReviewResearchGap] = Field(default_factory=list, max_length=50)
    unknowns: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> CompetitorUserReviewModelOutput:
        if len(self.summary_evidence_ids) != len(set(self.summary_evidence_ids)):
            raise ValueError("summary_evidence_ids must be unique")
        theme_ids = [item.theme_id for item in self.review_themes]
        if len(theme_ids) != len(set(theme_ids)):
            raise ValueError("theme_id must be unique")
        return self

    def cited_evidence_ids(self) -> set[str]:
        citations = set(self.summary_evidence_ids)
        for collection in (
            self.review_themes,
            self.contradictions,
            self.sample_limitations,
        ):
            for item in collection:
                citations.update(item.evidence_ids)
        return citations


class CompetitorUserReviewEvidenceCoverage(StrictModel):
    requested_product_count: int = Field(ge=0)
    represented_product_count: int = Field(ge=0)
    repeated_theme_product_count: int = Field(ge=0)
    available_evidence_count: int = Field(ge=0)
    included_evidence_count: int = Field(ge=0)
    cited_evidence_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    review_theme_count: int = Field(ge=0)
    single_report_theme_count: int = Field(ge=0)
    repeated_theme_count: int = Field(ge=0)
    positive_theme_count: int = Field(ge=0)
    negative_theme_count: int = Field(ge=0)
    mixed_theme_count: int = Field(ge=0)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CompetitorUserReviewPayload(StrictModel):
    schema_name: str = "competitor_user_review_intelligence"
    schema_version: str = "1.0"
    summary: str
    summary_evidence_ids: list[str]
    review_themes: list[ReviewTheme]
    contradictions: list[ReviewContradiction]
    sample_limitations: list[ReviewSampleLimitation]
    research_gaps: list[ReviewResearchGap]
    evidence_coverage: CompetitorUserReviewEvidenceCoverage
