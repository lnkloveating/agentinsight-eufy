from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.schemas.project import DecisionAction, ResearchBrief
from app.schemas.source_recovery import SourceRecovery
from app.workflows import (
    GateName,
    ResearchAgentType,
    StageDecision,
    WorkflowOutcome,
    WorkflowRunner,
    WorkflowSourceRecoveryRequest,
    compile_research_graph,
    create_initial_state,
)
from app.workflows.contracts import GateRequest, WorkflowNodeError
from app.workflows.planning import PLANNED_AGENT_TYPES
from tests.research_brief import home_safety_brief

from .workflow_runtime import TestAgentRuntime


def _brief() -> ResearchBrief:
    return home_safety_brief()


def _gate_request(result: dict[str, Any]) -> GateRequest:
    return GateRequest.model_validate(result["__interrupt__"][0].value)


def _source_request(result: dict[str, Any]) -> WorkflowSourceRecoveryRequest:
    return WorkflowSourceRecoveryRequest.model_validate(result["__interrupt__"][0].value)


def _decision(
    request: GateRequest,
    action: DecisionAction,
    *,
    selected: list[str] | None = None,
    affected: list[str] | None = None,
) -> dict[str, Any]:
    return StageDecision(
        decision_id=request.decision_id,
        gate=request.gate,
        action=action,
        actor="测试产品经理",
        reason=f"测试决定：{action}",
        selected_innovation_ids=selected or [],
        affected_task_ids=affected or [],
    ).model_dump(mode="json")


def _resolved_recovery(
    project_id: str,
    task_id: str,
    agent_type: str = "ecosystem_opportunity",
) -> dict[str, Any]:
    now = datetime.now(UTC)
    assessment = {
        "project_id": project_id,
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
            "source_recovery_id": "recovery_ecosystem",
            "project_id": project_id,
            "status": "resolved",
            "reason_code": "insufficient_information",
            "reason_message": "Evidence supplied.",
            "requirement_ids": [],
            "requested_fields": [],
            "affected_task_ids": [task_id],
            "affected_agent_types": [agent_type],
            "assessment_before": assessment,
            "current_assessment": assessment,
            "submissions": [],
            "resume_directive": {
                "ready": True,
                "mode": "targeted_retry",
                "affected_task_ids": [task_id],
                "affected_agent_types": [agent_type],
                "reason": "Evidence supplied; retry only ecosystem opportunity.",
            },
            "requested_by": "tester",
            "request_reason": "Complete AI-native evidence gaps.",
            "created_at": now,
            "updated_at": now,
        }
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_main_graph_runs_selected_opportunity_through_technical_feasibility() -> None:
    runtime = TestAgentRuntime()
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {"configurable": {"thread_id": "proj_happy"}}

    result = await graph.ainvoke(create_initial_state("proj_happy", _brief()), config)
    assert _gate_request(result).gate is GateName.BRIEF

    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.APPROVE)),
        config,
    )
    request = _gate_request(result)
    assert request.gate is GateName.AI_NATIVE_ECOSYSTEM
    assert request.summary["eligible_opportunity_ids"] == ["eco_continuous_guard"]
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY] == 1
    opportunity_context = runtime.contexts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY]
    assert opportunity_context.research_handoff is not None
    assert set(opportunity_context.upstream_artifacts) == {
        "user_research",
        "competitor_research",
    }

    result = await graph.ainvoke(
        Command(
            resume=_decision(
                request,
                DecisionAction.APPROVE,
                selected=["eco_continuous_guard"],
            )
        ),
        config,
    )

    assert result["outcome"] == WorkflowOutcome.AWAITING_SECURITY_POLICY
    assert result["terminal_reason"] == "security_policy_not_implemented"
    assert runtime.call_counts[ResearchAgentType.TECHNICAL_FEASIBILITY] == 1
    technical_context = runtime.contexts[ResearchAgentType.TECHNICAL_FEASIBILITY]
    assert technical_context.selected_innovation_ids == ["eco_continuous_guard"]
    assert set(technical_context.upstream_artifacts) == {"ecosystem_opportunity"}
    assert set(runtime.call_counts) == {
        ResearchAgentType.RESEARCH_MANAGER,
        *PLANNED_AGENT_TYPES,
        ResearchAgentType.TECHNICAL_FEASIBILITY,
    }
    assert len(result["decision_history"]) == 2


@pytest.mark.asyncio
async def test_evidence_gap_has_bounded_research_loop_and_no_fake_opportunity() -> None:
    runtime = TestAgentRuntime(evidence_ready_on_attempt=99)
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {
        "configurable": {"thread_id": "proj_insufficient"},
        "recursion_limit": 50,
    }

    result = await graph.ainvoke(create_initial_state("proj_insufficient", _brief()), config)
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.APPROVE)),
        config,
    )

    assert "__interrupt__" not in result
    assert result["outcome"] == WorkflowOutcome.INCONCLUSIVE
    assert result["iteration"] == 2
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 3
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 3
    assert ResearchAgentType.ECOSYSTEM_OPPORTUNITY not in runtime.call_counts


@pytest.mark.asyncio
async def test_technical_evidence_gap_enters_universal_source_recovery() -> None:
    runtime = TestAgentRuntime(technical_verdict="insufficient_evidence")
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {
        "configurable": {"thread_id": "proj_technical_recovery"},
        "recursion_limit": 50,
    }

    result = await graph.ainvoke(
        create_initial_state("proj_technical_recovery", _brief()), config
    )
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.APPROVE)),
        config,
    )
    result = await graph.ainvoke(
        Command(
            resume=_decision(
                _gate_request(result),
                DecisionAction.APPROVE,
                selected=["eco_continuous_guard"],
            )
        ),
        config,
    )

    request = _source_request(result)
    assert request.gap_ids == ["gap_technical_api"]
    assert request.affected_agent_types == ["technical_feasibility"]
    assert result["outcome"] == WorkflowOutcome.AWAITING_SOURCE_RECOVERY

    runtime.technical_verdict = "demo_feasible"
    result = await graph.ainvoke(
        Command(
            resume=_resolved_recovery(
                "proj_technical_recovery",
                "task_proj_technical_recovery_technical_feasibility",
                "technical_feasibility",
            )
        ),
        config,
    )

    assert result["outcome"] == WorkflowOutcome.AWAITING_SECURITY_POLICY
    assert runtime.call_counts[ResearchAgentType.TECHNICAL_FEASIBILITY] == 2
    assert runtime.call_counts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY] == 1


@pytest.mark.asyncio
async def test_audited_partial_competitor_gaps_reach_ecosystem_opportunity() -> None:
    runtime = TestAgentRuntime(competitor_ready_with_gaps=True)
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {"configurable": {"thread_id": "proj_competitor_gaps"}}

    result = await graph.ainvoke(create_initial_state("proj_competitor_gaps", _brief()), config)
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.APPROVE)),
        config,
    )

    assert _gate_request(result).gate is GateName.AI_NATIVE_ECOSYSTEM
    context = runtime.contexts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY]
    assert context.research_handoff is not None
    assert context.research_handoff.status == "ready_with_gaps"
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 1


@pytest.mark.asyncio
async def test_invalid_competitor_handoff_reruns_only_competitor() -> None:
    runtime = TestAgentRuntime(invalid_competitor_attempts=1)
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {
        "configurable": {"thread_id": "proj_invalid_competitor_handoff"},
        "recursion_limit": 50,
    }

    result = await graph.ainvoke(
        create_initial_state("proj_invalid_competitor_handoff", _brief()), config
    )
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.APPROVE)),
        config,
    )

    assert _gate_request(result).gate is GateName.AI_NATIVE_ECOSYSTEM
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 2
    assert runtime.call_counts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY] == 1


@pytest.mark.asyncio
async def test_sqlite_checkpoint_retries_only_failed_ecosystem_node(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "workflow-checkpoints.db"
    runtime = TestAgentRuntime(fail_once={ResearchAgentType.ECOSYSTEM_OPPORTUNITY})
    config = {"configurable": {"thread_id": "proj_retry"}}

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = compile_research_graph(runtime, checkpointer)
        first = await graph.ainvoke(create_initial_state("proj_retry", _brief()), config)
        with pytest.raises(WorkflowNodeError) as exc_info:
            await graph.ainvoke(
                Command(resume=_decision(_gate_request(first), DecisionAction.APPROVE)),
                config,
            )
        assert exc_info.value.node == "ecosystem_opportunity"

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        recovered_graph = compile_research_graph(runtime, checkpointer)
        recovered = await recovered_graph.ainvoke(None, config)

    assert _gate_request(recovered).gate is GateName.AI_NATIVE_ECOSYSTEM
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY] == 2


@pytest.mark.asyncio
async def test_ai_native_revision_reruns_only_ecosystem_opportunity() -> None:
    runtime = TestAgentRuntime()
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {
        "configurable": {"thread_id": "proj_revision"},
        "recursion_limit": 50,
    }

    result = await graph.ainvoke(create_initial_state("proj_revision", _brief()), config)
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.APPROVE)), config
    )
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.REVISE)), config
    )

    assert _gate_request(result).gate is GateName.AI_NATIVE_ECOSYSTEM
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY] == 2
    assert result["iteration"] == 1


@pytest.mark.asyncio
async def test_research_more_waits_for_source_recovery_then_retries_only_opportunity() -> None:
    runtime = TestAgentRuntime()
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {
        "configurable": {"thread_id": "proj_recovery"},
        "recursion_limit": 50,
    }

    result = await graph.ainvoke(create_initial_state("proj_recovery", _brief()), config)
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.APPROVE)), config
    )
    result = await graph.ainvoke(
        Command(resume=_decision(_gate_request(result), DecisionAction.RESEARCH_MORE)),
        config,
    )
    recovery_request = _source_request(result)
    assert recovery_request.gap_ids == ["gap_more_opportunities"]
    assert result["outcome"] == WorkflowOutcome.AWAITING_SOURCE_RECOVERY

    result = await graph.ainvoke(
        Command(
            resume=_resolved_recovery("proj_recovery", "task_proj_recovery_ecosystem_opportunity")
        ),
        config,
    )

    assert _gate_request(result).gate is GateName.AI_NATIVE_ECOSYSTEM
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY] == 2


@pytest.mark.asyncio
async def test_runner_exposes_checkpoint_without_leaking_langgraph_call_details() -> None:
    runtime = TestAgentRuntime()
    runner = WorkflowRunner(compile_research_graph(runtime, InMemorySaver()))

    result = await runner.start(create_initial_state("proj_runner", _brief()))
    snapshot = await runner.snapshot("proj_runner")

    assert _gate_request(result).gate is GateName.BRIEF
    assert snapshot.thread_id == "proj_runner"
    assert snapshot.checkpoint_id is not None
    assert snapshot.next_nodes == ["brief_gate"]
    assert snapshot.values["pending_gate"]["gate"] == "brief"
