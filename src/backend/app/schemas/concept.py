from pydantic import BaseModel, Field


class Concept(BaseModel):
    concept_id: str
    name: str
    target_user: str
    value_proposition: str
    supporting_evidence_ids: list[str]
    risks: list[str] = Field(default_factory=list)
    red_team_findings: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    status: str
