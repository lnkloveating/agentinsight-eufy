"""Build bounded commercial Evidence context from current ecosystem artifacts."""

from app.agents.ecosystem_opportunity import EcosystemOpportunityContextBuilder
from app.workflows.contracts import AgentEvidenceContext, ResearchArtifact, ResearchHandoff


class CommercialEvaluationContextBuilder:
    def __init__(self, ecosystem_context_builder: EcosystemOpportunityContextBuilder) -> None:
        self.ecosystem_context_builder = ecosystem_context_builder

    async def build(
        self,
        project_id: str,
        handoff: ResearchHandoff,
        artifacts: list[ResearchArtifact],
        supplemental_evidence_ids: list[str] | None = None,
    ) -> AgentEvidenceContext:
        expanded = handoff.model_copy(
            update={
                "supplemental_evidence_ids": list(
                    dict.fromkeys(
                        [
                            *handoff.supplemental_evidence_ids,
                            *(
                                evidence_id
                                for artifact in artifacts
                                for evidence_id in artifact.evidence_ids
                            ),
                            *(supplemental_evidence_ids or []),
                        ]
                    )
                )
            }
        )
        return (
            await self.ecosystem_context_builder.build(project_id, expanded)
        ).evidence_context
