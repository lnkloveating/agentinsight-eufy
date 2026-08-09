from datetime import UTC, datetime

import pytest

from app.schemas.source_recovery import SourceRecovery
from app.workflows.contracts import WorkflowContractError
from app.workflows.source_recovery import prepare_source_recovery_resume


def _recovery(*, ready: bool) -> SourceRecovery:
    now = datetime.now(UTC).isoformat()
    assessment = {
        "project_id": "proj_one",
        "status": "partial",
        "region": "US",
        "scope": None,
        "requirements": [],
        "required_count": 0,
        "satisfied_required_count": 0,
        "missing_required_count": 0,
        "unassigned_source_asset_ids": [],
        "missing_actions": [],
        "input_hash": "a" * 64,
        "evaluated_at": now,
    }
    return SourceRecovery.model_validate(
        {
            "source_recovery_id": "recovery_one",
            "project_id": "proj_one",
            "status": "resolved" if ready else "waiting_for_user_input",
            "reason_code": "insufficient_information",
            "reason_message": "missing",
            "failed_source_asset_id": "source_one",
            "failed_collection_job_id": "job_one",
            "requirement_ids": [],
            "requested_fields": [],
            "affected_task_ids": ["non-workflow-collection-task"],
            "affected_agent_types": ["competitor_research"],
            "assessment_before": assessment,
            "current_assessment": assessment,
            "submissions": [],
            "resume_directive": {
                "ready": ready,
                "mode": "targeted_retry" if ready else "none",
                "affected_task_ids": ["non-workflow-collection-task"],
                "affected_agent_types": ["competitor_research"],
                "reason": "resume" if ready else "wait",
            },
            "requested_by": "lead",
            "request_reason": "test",
            "created_at": now,
            "updated_at": now,
        }
    )


def _state() -> dict[str, object]:
    common = {
        "project_id": "proj_one",
        "goal": "test",
        "required_artifacts": [],
        "acceptance_checks": [],
    }
    return {
        "project_id": "proj_one",
        "iteration": 1,
        "task_plan": [
            {
                **common,
                "task_id": "task_user",
                "agent_type": "user_research",
            },
            {
                **common,
                "task_id": "task_competitor",
                "agent_type": "competitor_research",
            },
        ],
    }


def test_source_recovery_resume_maps_agent_type_to_only_affected_planned_task() -> None:
    update = prepare_source_recovery_resume(_state(), _recovery(ready=True))  # type: ignore[arg-type]

    assert update["affected_task_ids"] == ["task_competitor"]
    assert update["iteration"] == 2
    assert update["current_stage"] == "targeted_research"


def test_source_recovery_cannot_resume_before_user_input_or_decision() -> None:
    with pytest.raises(WorkflowContractError, match="not ready"):
        prepare_source_recovery_resume(_state(), _recovery(ready=False))  # type: ignore[arg-type]
