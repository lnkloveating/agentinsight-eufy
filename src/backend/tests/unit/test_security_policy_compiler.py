from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.agents.security_policy import (
    PolicyFallbackTrigger,
    SecurityPolicyCompiler,
    SecurityPolicyModelOutput,
    SecurityPolicyValidationError,
)
from app.agents.technical_feasibility import TechnicalFeasibilityOutputValidator
from app.core.config import Settings
from app.main import create_app
from app.workflows.contracts import AgentContext, ResearchAgentType, ResearchBudget, ResearchTask
from tests.unit.test_technical_feasibility_agent import (
    _context as technical_context,
)
from tests.unit.test_technical_feasibility_agent import (
    _fully_supported_graph,
)
from tests.unit.test_technical_feasibility_agent import (
    _model_output as technical_output,
)
from tests.unit.test_technical_feasibility_agent import (
    _task as technical_task,
)


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_security_policy",
        project_id="proj_ecosystem",
        agent_type=ResearchAgentType.SECURITY_POLICY,
        goal="Compile a safe dry-run policy.",
        budget=ResearchBudget(deadline_seconds=180),
    )


def _context() -> AgentContext:
    base = technical_context()
    opportunity = base.upstream_artifacts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value]
    technical = TechnicalFeasibilityOutputValidator().validate(
        technical_task(), base, _fully_supported_graph(), technical_output()
    )
    return AgentContext(
        project_id=base.project_id,
        brief=base.brief,
        iteration=0,
        upstream_artifacts={
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value: opportunity,
            ResearchAgentType.TECHNICAL_FEASIBILITY.value: technical.to_research_artifact(),
        },
        selected_innovation_ids=["eco_dynamic_1"],
        evidence_context=base.evidence_context,
        research_handoff=base.research_handoff,
    )


def _output() -> SecurityPolicyModelOutput:
    return SecurityPolicyModelOutput.model_validate(
        {
            "summary": "Compile the selected continuous home-safety opportunity.",
            "summary_evidence_ids": ["ev_device"],
            "policies": [
                {
                    "opportunity_id": "eco_dynamic_1",
                    "policy_name": "Continuous safety observation",
                    "objective": "Maintain an explicit uncertain household risk state.",
                    "state_variables": [
                        {
                            "key": "risk_state",
                            "value_type": "risk_level",
                            "description": "Current bounded risk state.",
                            "initial_value": "uncertain",
                            "retention_seconds": 3600,
                        }
                    ],
                    "signal_requests": [
                        {
                            "key": "motion_event",
                            "signal_type": "motion_event",
                            "source_role_id": "role_sensor_1",
                            "purpose": "Observe an authorized event without raw media.",
                            "freshness_seconds": 30,
                            "required": True,
                        }
                    ],
                    "risk_rules": [
                        {
                            "description": (
                                "Treat a present event as low risk pending confirmation."
                            ),
                            "conditions": [
                                {
                                    "reference": "signal:motion_event",
                                    "operator": "exists",
                                }
                            ],
                            "resulting_risk_level": "low",
                            "rationale": "Evidence supports metadata event availability.",
                            "evidence_ids": ["ev_device"],
                        }
                    ],
                    "intervention_ladder": [
                        {
                            "minimum_risk_level": "low",
                            "action": "continue_observing",
                            "human_approval_required": False,
                            "cooldown_seconds": 30,
                            "rationale": "Use only the lowest-risk authorized action.",
                        }
                    ],
                    "assumptions": [],
                    "evidence_ids": ["ev_device"],
                }
            ],
            "compilation_gaps": [],
            "unknowns": [],
        }
    )


def test_compiler_produces_deterministic_dry_run_policy_and_five_fallbacks() -> None:
    artifact = SecurityPolicyCompiler().compile(_task(), _context(), _output())
    policy = artifact.payload.policies[0]

    assert policy.execution_mode == "dry_run"
    assert len(policy.fallbacks) == 5
    assert {item.trigger for item in policy.fallbacks} == set(PolicyFallbackTrigger)
    assert any(item.kind == "dry_run_only" for item in policy.invariants)
    assert len(policy.dsl_hash) == 64
    assert artifact.payload.coverage.compiled_policy_count == 1


def test_compiler_rejects_signal_not_authorized_by_brief() -> None:
    raw = deepcopy(_output().model_dump(mode="json"))
    raw["policies"][0]["signal_requests"][0]["signal_type"] = "door_event"

    with pytest.raises(SecurityPolicyValidationError, match="outside the Research Brief"):
        SecurityPolicyCompiler().compile(
            _task(), _context(), SecurityPolicyModelOutput.model_validate(raw)
        )


def test_compiler_rejects_unknown_device_role_and_undefined_reference() -> None:
    raw = deepcopy(_output().model_dump(mode="json"))
    raw["policies"][0]["signal_requests"][0]["source_role_id"] = "role_invented"
    with pytest.raises(SecurityPolicyValidationError, match="absent"):
        SecurityPolicyCompiler().compile(
            _task(), _context(), SecurityPolicyModelOutput.model_validate(raw)
        )

    raw = deepcopy(_output().model_dump(mode="json"))
    raw["policies"][0]["risk_rules"][0]["conditions"][0]["reference"] = (
        "state:not_declared"
    )
    with pytest.raises(SecurityPolicyValidationError, match="undefined"):
        SecurityPolicyCompiler().compile(
            _task(), _context(), SecurityPolicyModelOutput.model_validate(raw)
        )


def test_model_cannot_supply_backend_owned_compiled_fields() -> None:
    raw = deepcopy(_output().model_dump(mode="json"))
    raw["policies"][0]["execution_mode"] = "live"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SecurityPolicyModelOutput.model_validate(raw)


def test_public_security_policy_routes_are_registered() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]
    assert "/api/v1/projects/{project_id}/agents/security-policy-compiler" in paths
    assert (
        "/api/v1/projects/{project_id}/agents/security-policy-compiler/artifacts"
        in paths
    )


def test_checked_in_openapi_exposes_security_policy_contract() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    document = yaml.safe_load(
        (repository_root / "docs" / "api" / "openapi.yaml").read_text(
            encoding="utf-8"
        )
    )
    path = document["paths"]["/projects/{project_id}/agents/security-policy-compiler"]
    assert path["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SecurityPolicyRunCreate"
    }
    policy = document["components"]["schemas"]["CompiledSecurityPolicy"]
    assert policy["properties"]["execution_mode"]["const"] == "dry_run"
    fallback = document["components"]["schemas"]["PolicyFallbackTrigger"]
    assert set(fallback["enum"]) == {item.value for item in PolicyFallbackTrigger}
