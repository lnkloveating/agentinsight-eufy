"""Build a bounded Evidence context for Red Team Policy Revision."""

from app.agents.commercial_evaluation_v2 import CommercialEvaluationContextBuilder
from app.workflows.contracts import AgentEvidenceContext, ResearchArtifact, ResearchHandoff


class RedTeamContextBuilder:
    def __init__(self, commercial_builder: CommercialEvaluationContextBuilder) -> None:
        self.commercial_builder = commercial_builder

    async def build(
        self,
        project_id: str,
        handoff: ResearchHandoff,
        artifacts: list[ResearchArtifact],
        supplemental_evidence_ids: list[str] | None = None,
    ) -> AgentEvidenceContext:
        return await self.commercial_builder.build(
            project_id,
            handoff,
            artifacts,
            supplemental_evidence_ids,
        )
