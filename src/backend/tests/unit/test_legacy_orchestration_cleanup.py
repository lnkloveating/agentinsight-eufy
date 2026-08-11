from pathlib import Path

import yaml

from app.application.runtime.gateway import AGENT_NAMES
from app.schemas.source_recovery import RecoverableAgentType
from app.workflows import contracts, gates
from app.workflows.context import CONTEXT_POLICY
from app.workflows.contracts import ResearchAgentType

_REMOVED_V1_AGENT_TYPES = {
    "candidate_synthesis",
    "validation",
    "final_synthesis",
}


def test_v1_orchestration_roles_are_removed_from_runtime_contracts() -> None:
    research_types = {item.value for item in ResearchAgentType}
    recoverable_types = {item.value for item in RecoverableAgentType}

    assert research_types.isdisjoint(_REMOVED_V1_AGENT_TYPES)
    assert recoverable_types.isdisjoint(_REMOVED_V1_AGENT_TYPES)
    assert set(CONTEXT_POLICY) == set(ResearchAgentType)
    assert set(AGENT_NAMES) == set(ResearchAgentType)


def test_red_team_keeps_current_upstream_context_without_v1_directive() -> None:
    assert CONTEXT_POLICY[ResearchAgentType.RED_TEAM] == {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        ResearchAgentType.TECHNICAL_FEASIBILITY,
        ResearchAgentType.SECURITY_POLICY,
        ResearchAgentType.POLICY_VERIFICATION,
        ResearchAgentType.COMMERCIAL_EVALUATION,
    }
    assert not hasattr(contracts, "RedTeamDirective")
    assert not hasattr(gates, "parse_red_team_directive")


def test_checked_in_openapi_only_exposes_current_recoverable_agents() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    document = yaml.safe_load(
        (repository_root / "docs" / "api" / "openapi.yaml").read_text(
            encoding="utf-8"
        )
    )
    exposed = set(
        document["components"]["parameters"]["RecoverableAgentType"]["schema"][
            "enum"
        ]
    )

    assert exposed == {item.value for item in RecoverableAgentType}
    assert "red_team" in exposed
