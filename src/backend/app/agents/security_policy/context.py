"""Build bounded Evidence context for Security Policy compilation."""

from app.agents.technical_feasibility import TechnicalFeasibilityContextBuilder
from app.workflows.contracts import AgentEvidenceContext, ResearchArtifact, ResearchHandoff


class SecurityPolicyContextBuilder:
    def __init__(
        self, technical_context_builder: TechnicalFeasibilityContextBuilder
    ) -> None:
        self.technical_context_builder = technical_context_builder

    async def build(
        self,
        project_id: str,
        handoff: ResearchHandoff,
        opportunity_artifact: ResearchArtifact,
        technical_artifact: ResearchArtifact,
        supplemental_evidence_ids: list[str] | None = None,
    ) -> AgentEvidenceContext:
        expanded = handoff.model_copy(
            update={
                "supplemental_evidence_ids": list(
                    dict.fromkeys(
                        [
                            *handoff.supplemental_evidence_ids,
                            *technical_artifact.evidence_ids,
                            *(supplemental_evidence_ids or []),
                        ]
                    )
                )
            }
        )
        bundle = await self.technical_context_builder.build(
            project_id,
            expanded,
            opportunity_artifact,
        )
        return bundle.evidence_context
