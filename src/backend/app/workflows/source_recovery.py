"""将持久化资料恢复结果投影为 LangGraph 定向恢复更新。"""

from typing import Any

from app.schemas.source_recovery import SourceRecovery, SourceRecoveryResumeMode
from app.workflows.contracts import (
    ResearchAgentType,
    ResearchHandoff,
    ResearchState,
    ResearchTask,
    WorkflowContractError,
    WorkflowEvent,
)


def prepare_source_recovery_resume(
    state: ResearchState,
    recovery: SourceRecovery,
) -> dict[str, Any]:
    """只选择当前 Task Plan 内且属于受影响 Agent 的任务。"""

    directive = recovery.resume_directive
    if not directive.ready or directive.mode is SourceRecoveryResumeMode.NONE:
        raise WorkflowContractError("source recovery is not ready to resume")
    if recovery.project_id != state.get("project_id"):
        raise WorkflowContractError("source recovery belongs to another project")

    tasks = [ResearchTask.model_validate(item) for item in state.get("task_plan", [])]
    requested_agents = {ResearchAgentType(item) for item in directive.affected_agent_types}
    planned_ids = {task.task_id for task in tasks}
    affected = {
        task.task_id for task in tasks if task.agent_type in requested_agents
    } | {task_id for task_id in directive.affected_task_ids if task_id in planned_ids}
    if not affected and directive.mode is SourceRecoveryResumeMode.TARGETED_RETRY:
        raise WorkflowContractError("source recovery does not match any planned task")

    update: dict[str, Any] = {
        "affected_task_ids": sorted(affected),
        "iteration": state.get("iteration", 0) + 1,
        "current_stage": (
            "targeted_research"
            if directive.mode is SourceRecoveryResumeMode.TARGETED_RETRY
            else "research_with_gaps"
        ),
        "node_history": [
            WorkflowEvent(
                event_type="source_recovery_resume_prepared",
                node="source_recovery",
                status=directive.mode,
                message=directive.reason,
            ).model_dump(mode="json")
        ],
    }
    raw_handoff = state.get("research_handoff")
    if raw_handoff is not None:
        handoff = ResearchHandoff.model_validate(raw_handoff)
        recovered_evidence_ids = [
            evidence_id
            for submission in recovery.submissions
            for evidence_id in submission.evidence_ids
        ]
        update["research_handoff"] = handoff.model_copy(
            update={
                "supplemental_evidence_ids": list(
                    dict.fromkeys(
                        [
                            *handoff.supplemental_evidence_ids,
                            *recovered_evidence_ids,
                        ]
                    )
                )
            }
        ).model_dump(mode="json")
    return update
