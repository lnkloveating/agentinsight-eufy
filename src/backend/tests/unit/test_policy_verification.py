from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from app.agents.policy_verification import (
    PolicyVerificationError,
    PolicyVerificationRunCreate,
    PolicyVerificationScenarioCreate,
    SecurityPolicyVerificationEngine,
    VerificationStatus,
)
from app.agents.security_policy import SecurityPolicyCompiler, SecurityPolicyModelOutput
from app.application.source_recovery.gaps import AgentGapProjector
from app.core.config import Settings
from app.main import create_app
from app.schemas.source_recovery import RecoverableAgentType
from app.workflows.contracts import ResearchAgentType, ResearchBudget, ResearchTask
from tests.unit.test_security_policy_compiler import (
    _context as policy_context,
)
from tests.unit.test_security_policy_compiler import (
    _output as policy_output,
)
from tests.unit.test_security_policy_compiler import (
    _task as policy_task,
)


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_policy_verification",
        project_id="proj_ecosystem",
        agent_type=ResearchAgentType.POLICY_VERIFICATION,
        goal="Verify compiled policy behavior.",
        budget=ResearchBudget(deadline_seconds=60),
    )


def _policy(output: SecurityPolicyModelOutput | None = None):
    return SecurityPolicyCompiler().compile(
        policy_task(), policy_context(), output or policy_output()
    )


def test_generated_suite_exercises_rule_and_all_five_fallbacks() -> None:
    artifact = SecurityPolicyVerificationEngine().verify(
        _task(), _policy(), PolicyVerificationRunCreate()
    )

    assert artifact.payload.verification_status is VerificationStatus.PASSED
    assert artifact.payload.coverage.scenario_count == 6
    assert artifact.payload.coverage.passed_count == 6
    assert artifact.payload.coverage.fallback_types_covered == 5
    assert artifact.payload.coverage.user_defined_count == 0
    assert all(result.assertions for result in artifact.payload.results)


def test_user_scenario_can_expose_policy_failure_without_model_judging_it() -> None:
    policy = _policy()
    policy_id = policy.payload.policies[0].policy_id
    request = PolicyVerificationRunCreate(
        scenarios=[
            PolicyVerificationScenarioCreate(
                name="Normal movement must not escalate",
                policy_id=policy_id,
                updates=[
                    {
                        "reference": "signal:motion_event",
                        "value": True,
                    }
                ],
                expected_risk_level="informational",
                rationale="User-defined false-positive challenge.",
                evidence_ids=["ev_device"],
            )
        ]
    )
    artifact = SecurityPolicyVerificationEngine().verify(_task(), policy, request)

    assert artifact.payload.verification_status is VerificationStatus.FAILED
    user_scenario = next(
        item for item in artifact.payload.scenarios if item.origin == "user"
    )
    result = next(
        item
        for item in artifact.payload.results
        if item.scenario_id == user_scenario.scenario_id
    )
    assert any(not assertion.passed for assertion in result.assertions)


def test_user_scenario_is_bounded_to_policy_references_and_evidence() -> None:
    policy = _policy()
    policy_id = policy.payload.policies[0].policy_id
    invalid_reference = PolicyVerificationRunCreate.model_validate(
        {
            "scenarios": [
                {
                    "name": "Invented signal",
                    "policy_id": policy_id,
                    "updates": [{"reference": "signal:secret_camera", "value": True}],
                    "expected_risk_level": "low",
                    "rationale": "Must be rejected.",
                }
            ]
        }
    )
    with pytest.raises(PolicyVerificationError, match="outside the policy"):
        SecurityPolicyVerificationEngine().verify(_task(), policy, invalid_reference)

    invalid_evidence = PolicyVerificationRunCreate.model_validate(
        {
            "scenarios": [
                {
                    "name": "Foreign evidence",
                    "policy_id": policy_id,
                    "updates": [{"reference": "signal:motion_event", "value": True}],
                    "expected_risk_level": "low",
                    "rationale": "Must be rejected.",
                    "evidence_ids": ["ev_foreign"],
                }
            ]
        }
    )
    with pytest.raises(PolicyVerificationError, match="outside the source policy"):
        SecurityPolicyVerificationEngine().verify(_task(), policy, invalid_evidence)


def test_temporal_condition_produces_timestamped_trace() -> None:
    raw = deepcopy(policy_output().model_dump(mode="json"))
    condition = raw["policies"][0]["risk_rules"][0]["conditions"][0]
    condition["operator"] = "changed"
    condition["value"] = None
    policy = _policy(SecurityPolicyModelOutput.model_validate(raw))

    artifact = SecurityPolicyVerificationEngine().verify(
        _task(), policy, PolicyVerificationRunCreate()
    )

    assert artifact.payload.verification_status is VerificationStatus.PASSED
    risk_result = next(
        item for item in artifact.payload.results if item.category == "risk_rule"
    )
    assert risk_result.trace[0].event.startswith("t+1s")


def test_unsynthesizable_condition_becomes_gap_and_source_recovery_item() -> None:
    raw = deepcopy(policy_output().model_dump(mode="json"))
    condition = raw["policies"][0]["risk_rules"][0]["conditions"][0]
    condition["operator"] = "not_exists"
    condition["value"] = None
    policy = _policy(SecurityPolicyModelOutput.model_validate(raw))

    artifact = SecurityPolicyVerificationEngine().verify(
        _task(), policy, PolicyVerificationRunCreate()
    )

    assert artifact.payload.verification_status is VerificationStatus.CONDITIONALLY_PASSED
    assert artifact.payload.validation_gaps
    assert artifact.unknowns == [artifact.payload.validation_gaps[0].question]
    projected = AgentGapProjector().project(
        artifact.to_research_artifact(), RecoverableAgentType.POLICY_VERIFICATION
    )
    assert projected[0].affected_candidate_ids == [policy.payload.policies[0].policy_id]


def test_generated_scenario_ids_are_deterministic_across_runs() -> None:
    engine = SecurityPolicyVerificationEngine()
    policy = _policy()
    first = engine.verify(_task(), policy, PolicyVerificationRunCreate(), iteration=0)
    second = engine.verify(_task(), policy, PolicyVerificationRunCreate(), iteration=1)

    assert first.artifact_id != second.artifact_id
    assert [item.scenario_id for item in first.payload.scenarios] == [
        item.scenario_id for item in second.payload.scenarios
    ]


def test_public_policy_verification_routes_are_registered() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]
    assert "/api/v1/projects/{project_id}/workflows/security-policy-verification" in paths
    assert (
        "/api/v1/projects/{project_id}/workflows/security-policy-verification/artifacts"
        in paths
    )


def test_checked_in_openapi_exposes_dry_run_verification_contract() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    document = yaml.safe_load(
        (repository_root / "docs" / "api" / "openapi.yaml").read_text(
            encoding="utf-8"
        )
    )
    path = document["paths"][
        "/projects/{project_id}/workflows/security-policy-verification"
    ]
    assert path["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PolicyVerificationRunCreate"
    }
    assert set(document["components"]["schemas"]["VerificationStatus"]["enum"]) == {
        item.value for item in VerificationStatus
    }
