from copy import deepcopy

from app.workflows.ai_native_gate import (
    AINativeCandidateStatus,
    AINativeCriterion,
    AINativeEcosystemGate,
)
from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus
from tests.integration.workflow_runtime import _ecosystem_opportunity_payload


def _artifact(payload: dict[str, object] | None = None) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id="artifact_ecosystem",
        task_id="task_ecosystem",
        artifact_type="ecosystem_opportunity",
        status=ResearchTaskStatus.PARTIAL,
        payload=payload
        or _ecosystem_opportunity_payload(["ev_test_user_research", "ev_test_competitor_research"]),
        evidence_ids=["ev_test_user_research", "ev_test_competitor_research"],
        quality_score=80,
    )


def test_grounded_closed_loop_reaches_human_semantic_review() -> None:
    result = AINativeEcosystemGate().evaluate(_artifact())

    assert result.ready_for_human_gate is True
    assert result.eligible_opportunity_ids == ["eco_continuous_guard"]
    assessment = result.assessments[0]
    assert assessment.status is AINativeCandidateStatus.HUMAN_REVIEW_REQUIRED
    assert all(item.passed for item in assessment.criteria)
    assert {item.question_id.split("_")[1] for item in assessment.human_review_questions} >= {
        "open",
        "persistent",
        "active",
        "failure",
    }
    assert result.source_recovery_gap_ids == ["gap_more_opportunities"]


def test_notification_feature_cannot_masquerade_as_ai_native_ecosystem() -> None:
    payload = deepcopy(
        _ecosystem_opportunity_payload(["ev_test_user_research", "ev_test_competitor_research"])
    )
    candidate = payload["opportunities"][0]  # type: ignore[index]
    candidate["scope_level"] = "device_feature"  # type: ignore[index]
    candidate["ai_native_case"]["ai_removal_test"][  # type: ignore[index]
        "core_value_survives_without_ai"
    ] = True
    candidate["ai_native_case"]["learning_or_revision_loop"] = []  # type: ignore[index]
    candidate["validation_plan"]["required_scenario_types"] = ["normal"]  # type: ignore[index]
    payload["coverage"]["ecosystem_service_count"] = 0  # type: ignore[index]

    result = AINativeEcosystemGate().evaluate(_artifact(payload))

    assert result.ready_for_human_gate is False
    assessment = result.assessments[0]
    assert assessment.status is AINativeCandidateStatus.BLOCKED
    failed = {item.criterion for item in assessment.criteria if not item.passed}
    assert failed >= {
        AINativeCriterion.ECOSYSTEM_SCOPE,
        AINativeCriterion.AI_REMOVAL,
        AINativeCriterion.REVISION_LOOP,
        AINativeCriterion.PREDEPLOYMENT_VALIDATION,
    }
    assert result.revision_requests[0].affected_task_ids == ["task_ecosystem"]


def test_missing_flow_privacy_and_human_review_boundary_is_blocked() -> None:
    payload = deepcopy(
        _ecosystem_opportunity_payload(["ev_test_user_research", "ev_test_competitor_research"])
    )
    candidate = payload["opportunities"][0]  # type: ignore[index]
    candidate["ecosystem_blueprint"]["cross_device_information_flows"][0][  # type: ignore[index]
        "privacy_constraints"
    ] = []
    candidate["validation_plan"]["human_review_points"] = []  # type: ignore[index]

    result = AINativeEcosystemGate().evaluate(_artifact(payload))

    issues = set(result.assessments[0].blocking_issues)
    assert "missing_privacy_offline_or_failure_fallback" in issues
    assert "missing_permission_safety_or_human_review_boundary" in issues


def test_revision_request_id_is_stable_for_the_same_failure() -> None:
    payload = deepcopy(
        _ecosystem_opportunity_payload(["ev_test_user_research", "ev_test_competitor_research"])
    )
    candidate = payload["opportunities"][0]  # type: ignore[index]
    candidate["ai_native_case"]["learning_or_revision_loop"] = []  # type: ignore[index]

    first = AINativeEcosystemGate().evaluate(_artifact(payload))
    second = AINativeEcosystemGate().evaluate(_artifact(payload))

    assert (
        first.revision_requests[0].revision_request_id
        == second.revision_requests[0].revision_request_id
    )
