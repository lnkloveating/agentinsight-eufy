"""Evidence-bounded ecosystem opportunity Agent."""

from app.agents.ecosystem_opportunity.adapter import (
    EcosystemOpportunityModelAgentAdapter,
)
from app.agents.ecosystem_opportunity.context import (
    DeviceCapabilityFact,
    DeviceCapabilityGraphContext,
    EcosystemOpportunityContextBuilder,
    EcosystemOpportunityContextBundle,
)
from app.agents.ecosystem_opportunity.contracts import (
    AINativeCase,
    AIRemovalTest,
    CrossDeviceInformationFlow,
    DeviceRoleType,
    EcosystemBlueprint,
    EcosystemDeploymentTarget,
    EcosystemGateStatus,
    EcosystemOpportunityArtifact,
    EcosystemOpportunityCandidate,
    EcosystemOpportunityCoverage,
    EcosystemOpportunityGap,
    EcosystemOpportunityModelCandidate,
    EcosystemOpportunityModelGap,
    EcosystemOpportunityModelOutput,
    EcosystemOpportunityPayload,
    EcosystemScenarioType,
    EcosystemValidationPlan,
    RequiredDeviceRole,
    SolutionScope,
    ecosystem_opportunity_gap_id,
)
from app.agents.ecosystem_opportunity.prompt import register_ecosystem_opportunity_prompt
from app.agents.ecosystem_opportunity.validation import (
    EcosystemOpportunityOutputValidator,
    EcosystemOpportunityValidationError,
)

__all__ = [
    "AINativeCase",
    "AIRemovalTest",
    "CrossDeviceInformationFlow",
    "DeviceCapabilityFact",
    "DeviceCapabilityGraphContext",
    "DeviceRoleType",
    "EcosystemBlueprint",
    "EcosystemDeploymentTarget",
    "EcosystemGateStatus",
    "EcosystemOpportunityArtifact",
    "EcosystemOpportunityCandidate",
    "EcosystemOpportunityCoverage",
    "EcosystemOpportunityContextBuilder",
    "EcosystemOpportunityContextBundle",
    "EcosystemOpportunityGap",
    "EcosystemOpportunityModelCandidate",
    "EcosystemOpportunityModelAgentAdapter",
    "EcosystemOpportunityModelGap",
    "EcosystemOpportunityModelOutput",
    "EcosystemOpportunityPayload",
    "EcosystemOpportunityOutputValidator",
    "EcosystemOpportunityValidationError",
    "EcosystemScenarioType",
    "EcosystemValidationPlan",
    "RequiredDeviceRole",
    "SolutionScope",
    "ecosystem_opportunity_gap_id",
    "register_ecosystem_opportunity_prompt",
]
