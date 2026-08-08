"""官方产品情报专家的强类型模型输出与结构化 Payload。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OfficialFactType(StrEnum):
    CAPABILITY = "capability"
    SPECIFICATION = "specification"
    COMPATIBILITY = "compatibility"
    LIMITATION = "limitation"
    AVAILABILITY = "availability"


class GapSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CitedOfficialItem(StrictModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=30)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class OfficialProductFact(CitedOfficialItem):
    fact_id: str = Field(min_length=1, max_length=80)
    fact_type: OfficialFactType
    field_name: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=2_000)
    qualifiers: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)


class OfficialProductRecord(CitedOfficialItem):
    """scope_label 必须原样对应主管请求，避免模型悄悄替换比较对象。"""

    scope_label: str = Field(min_length=1, max_length=240)
    official_name: str = Field(min_length=1, max_length=240)
    model_numbers: list[str] = Field(default_factory=list, max_length=30)
    facts: list[OfficialProductFact] = Field(default_factory=list, max_length=100)
    unknown_fields: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> OfficialProductRecord:
        if len(self.model_numbers) != len(set(self.model_numbers)):
            raise ValueError("model_numbers must be unique")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("fact_ids must be unique within a product")
        return self


class OfficialContradiction(CitedOfficialItem):
    statement: str = Field(min_length=1, max_length=2_000)


class OfficialResearchGap(StrictModel):
    scope_label: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=1_500)
    reason: str = Field(min_length=1, max_length=1_500)
    severity: GapSeverity
    recommended_source_types: list[str] = Field(default_factory=list, max_length=20)


class OfficialProductModelOutput(StrictModel):
    """模型输出；状态、覆盖率、质量分和最终 Findings 均由后端生成。"""

    summary: str = Field(min_length=1, max_length=4_000)
    summary_evidence_ids: list[str] = Field(min_length=1, max_length=30)
    products: list[OfficialProductRecord] = Field(default_factory=list, max_length=50)
    contradictions: list[OfficialContradiction] = Field(default_factory=list, max_length=30)
    research_gaps: list[OfficialResearchGap] = Field(default_factory=list, max_length=50)
    unknowns: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> OfficialProductModelOutput:
        if len(self.summary_evidence_ids) != len(set(self.summary_evidence_ids)):
            raise ValueError("summary_evidence_ids must be unique")
        labels = [product.scope_label for product in self.products]
        if len(labels) != len(set(labels)):
            raise ValueError("scope_label must be unique")
        return self

    def cited_evidence_ids(self) -> set[str]:
        citations = set(self.summary_evidence_ids)
        for product in self.products:
            citations.update(product.evidence_ids)
            for fact in product.facts:
                citations.update(fact.evidence_ids)
        for contradiction in self.contradictions:
            citations.update(contradiction.evidence_ids)
        return citations


class OfficialProductEvidenceCoverage(StrictModel):
    requested_product_count: int = Field(ge=0)
    represented_product_count: int = Field(ge=0)
    available_evidence_count: int = Field(ge=0)
    included_evidence_count: int = Field(ge=0)
    cited_evidence_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    vendor_claim_count: int = Field(ge=0)
    fact_count: int = Field(ge=0)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class OfficialProductPayload(StrictModel):
    schema_name: str = "official_product_intelligence"
    schema_version: str = "1.0"
    summary: str
    summary_evidence_ids: list[str]
    products: list[OfficialProductRecord]
    contradictions: list[OfficialContradiction]
    research_gaps: list[OfficialResearchGap]
    evidence_coverage: OfficialProductEvidenceCoverage
