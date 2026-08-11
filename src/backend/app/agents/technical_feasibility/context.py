"""Build bounded Evidence and Device Capability Graph context for feasibility."""

from pydantic import BaseModel, ConfigDict

from app.agents.ecosystem_opportunity import (
    DeviceCapabilityGraphContext,
    EcosystemOpportunityContextBuilder,
)
from app.workflows.contracts import AgentEvidenceContext, ResearchArtifact, ResearchHandoff


class TechnicalFeasibilityContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_context: AgentEvidenceContext
    capability_graph: DeviceCapabilityGraphContext


class TechnicalFeasibilityContextBuilder:
    def __init__(self, ecosystem_context_builder: EcosystemOpportunityContextBuilder) -> None:
        self.ecosystem_context_builder = ecosystem_context_builder

    async def build(
        self,
        project_id: str,
        handoff: ResearchHandoff,
        opportunity_artifact: ResearchArtifact,
        supplemental_evidence_ids: list[str] | None = None,
    ) -> TechnicalFeasibilityContextBundle:
        expanded = handoff.model_copy(
            update={
                "supplemental_evidence_ids": list(
                    dict.fromkeys(
                        [
                            *handoff.supplemental_evidence_ids,
                            *opportunity_artifact.evidence_ids,
                            *(supplemental_evidence_ids or []),
                        ]
                    )
                )
            }
        )
        bundle = await self.ecosystem_context_builder.build(project_id, expanded)
        return TechnicalFeasibilityContextBundle(
            evidence_context=bundle.evidence_context,
            capability_graph=bundle.capability_graph,
        )
