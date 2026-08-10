"""Ecosystem-level solution opportunity contracts (public domain vocabulary only).

This package defines the strong, evidence-bounded contracts for the ecosystem direction.
It intentionally contains no Prompt, model Adapter, Agent Service, FastAPI route, deterministic
AI-native gate or Device Capability Graph. Those arrive in later branches.
"""

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

__all__ = [
    "AINativeCase",
    "AIRemovalTest",
    "CrossDeviceInformationFlow",
    "DeviceRoleType",
    "EcosystemBlueprint",
    "EcosystemDeploymentTarget",
    "EcosystemGateStatus",
    "EcosystemOpportunityArtifact",
    "EcosystemOpportunityCandidate",
    "EcosystemOpportunityCoverage",
    "EcosystemOpportunityGap",
    "EcosystemOpportunityModelCandidate",
    "EcosystemOpportunityModelGap",
    "EcosystemOpportunityModelOutput",
    "EcosystemOpportunityPayload",
    "EcosystemScenarioType",
    "EcosystemValidationPlan",
    "RequiredDeviceRole",
    "SolutionScope",
    "ecosystem_opportunity_gap_id",
]
