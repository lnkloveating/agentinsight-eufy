from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.schemas.project import DecisionAction, ResearchBrief
from app.workflows import (
    GateName,
    ResearchAgentType,
    StageDecision,
    WorkflowOutcome,
    WorkflowRunner,
    compile_research_graph,
    create_initial_state,
)
from app.workflows.contracts import GateRequest, WorkflowNodeError
from app.workflows.planning import PLANNED_AGENT_TYPES

from .workflow_runtime import TestAgentRuntime


def _brief() -> ResearchBrief:
    return ResearchBrief(
        question="北美家庭安防中有哪些值得验证的事件理解机会？",
        category="家庭安防",
        target_user="北美家庭安防用户",
        region="北美",
        scenarios=["包裹", "车库门", "门口徘徊"],
        constraints=["证据优先", "隐私优先"],
        focus_dimensions=["用户", "竞品", "技术", "商业"],
    )


def _request(result: dict[str, Any]) -> GateRequest:
    interrupts = result["__interrupt__"]
    return GateRequest.model_validate(interrupts[0].value)


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


@pytest.mark.asyncio
async def test_complete_graph_pauses_at_three_gates_and_runs_all_agents() -> None:
    runtime = TestAgentRuntime()
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {"configurable": {"thread_id": "proj_happy"}}

    result = await graph.ainvoke(create_initial_state("proj_happy", _brief()), config)
    brief_request = _request(result)
    assert brief_request.gate is GateName.BRIEF

    result = await graph.ainvoke(
        Command(resume=_decision(brief_request, DecisionAction.APPROVE)), config
    )
    scenario_request = _request(result)
    assert scenario_request.gate is GateName.SCENARIO
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 1
    assert runtime.calls.index(ResearchAgentType.PRODUCT_TECHNICAL) > runtime.calls.index(
        ResearchAgentType.COMPETITOR_RESEARCH
    )
    product_context = runtime.contexts[ResearchAgentType.PRODUCT_TECHNICAL]
    assert product_context.research_handoff is not None
    assert product_context.research_handoff.status == "ready"
    assert set(product_context.upstream_artifacts) == {
        "user_research",
        "competitor_research",
    }
    assert product_context.research_handoff.merged_evidence_ids == [
        "ev_test_competitor_research",
        "ev_test_user_research",
    ]
    assert runtime.calls.index(ResearchAgentType.COMMERCIAL_EVALUATION) > runtime.calls.index(
        ResearchAgentType.PRODUCT_TECHNICAL
    )
    assert runtime.calls.index(ResearchAgentType.RED_TEAM) > runtime.calls.index(
        ResearchAgentType.COMMERCIAL_EVALUATION
    )

    result = await graph.ainvoke(
        Command(
            resume=_decision(
                scenario_request,
                DecisionAction.APPROVE,
                selected=["inv_one"],
            )
        ),
        config,
    )
    final_request = _request(result)
    assert final_request.gate is GateName.FINAL
    assert runtime.contexts[ResearchAgentType.VALIDATION].selected_innovation_ids == ["inv_one"]

    result = await graph.ainvoke(
        Command(resume=_decision(final_request, DecisionAction.APPROVE)), config
    )

    assert result["outcome"] == WorkflowOutcome.COMPLETED
    assert result["terminal_reason"] == "final_approved"
    assert set(runtime.call_counts) == {ResearchAgentType.RESEARCH_MANAGER, *PLANNED_AGENT_TYPES}
    assert len(result["decision_history"]) == 3


@pytest.mark.asyncio
async def test_evidence_gap_has_bounded_research_loop_and_no_fake_candidates() -> None:
    runtime = TestAgentRuntime(evidence_ready_on_attempt=99)
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {
        "configurable": {"thread_id": "proj_insufficient"},
        "recursion_limit": 50,
    }

    result = await graph.ainvoke(create_initial_state("proj_insufficient", _brief()), config)
    request = _request(result)
    result = await graph.ainvoke(
        Command(resume=_decision(request, DecisionAction.APPROVE)), config
    )

    assert "__interrupt__" not in result
    assert result["outcome"] == WorkflowOutcome.INCONCLUSIVE
    assert result["terminal_reason"] == "research_budget_exhausted_or_evidence_insufficient"
    assert result["iteration"] == 2
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 3
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 3
    assert ResearchAgentType.PRODUCT_TECHNICAL not in runtime.call_counts
    assert "product_technical" not in result["artifacts"]


@pytest.mark.asyncio
async def test_audited_partial_competitor_gaps_reach_product_technical() -> None:
    runtime = TestAgentRuntime(competitor_ready_with_gaps=True)
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {"configurable": {"thread_id": "proj_competitor_gaps"}}

    result = await graph.ainvoke(
        create_initial_state("proj_competitor_gaps", _brief()), config
    )
    result = await graph.ainvoke(
        Command(resume=_decision(_request(result), DecisionAction.APPROVE)), config
    )

    assert _request(result).gate is GateName.SCENARIO
    context = runtime.contexts[ResearchAgentType.PRODUCT_TECHNICAL]
    assert context.research_handoff is not None
    assert context.research_handoff.status == "ready_with_gaps"
    projection = context.research_handoff.competitor_projection
    assert projection is not None
    assert projection.opportunity_signal_ids == ["signal_package_context"]
    assert projection.gaps[0].scope_label == "Test Doorbell"
    assert projection.gaps[0].missing_dimensions == ["user_review"]
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
        Command(resume=_decision(_request(result), DecisionAction.APPROVE)), config
    )

    assert _request(result).gate is GateName.SCENARIO
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 2
    product_context = runtime.contexts[ResearchAgentType.PRODUCT_TECHNICAL]
    assert product_context.research_handoff is not None
    assert product_context.research_handoff.status == "ready"
    skipped = [
        event
        for event in result["node_history"]
        if event["event_type"] == "agent_node_skipped"
    ]
    assert any(event["task_id"].endswith("_user") for event in skipped)


@pytest.mark.asyncio
async def test_sqlite_checkpoint_retries_only_failed_parallel_node(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "workflow-checkpoints.db"
    runtime = TestAgentRuntime(fail_once={ResearchAgentType.COMPETITOR_RESEARCH})
    config = {"configurable": {"thread_id": "proj_retry"}}

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = compile_research_graph(runtime, checkpointer)
        first = await graph.ainvoke(create_initial_state("proj_retry", _brief()), config)
        brief_request = _request(first)
        with pytest.raises(WorkflowNodeError) as exc_info:
            await graph.ainvoke(
                Command(resume=_decision(brief_request, DecisionAction.APPROVE)), config
            )
        assert exc_info.value.node == "competitor_research_a2a"

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        recovered_graph = compile_research_graph(runtime, checkpointer)
        recovered = await recovered_graph.ainvoke(None, config)

    assert _request(recovered).gate is GateName.SCENARIO
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 1
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 2
    recovered_context = runtime.contexts[ResearchAgentType.PRODUCT_TECHNICAL]
    assert recovered_context.research_handoff is not None
    assert recovered_context.research_handoff.status == "ready"


@pytest.mark.asyncio
async def test_scenario_research_more_reruns_only_affected_research_agent() -> None:
    runtime = TestAgentRuntime()
    graph = compile_research_graph(runtime, InMemorySaver())
    config = {
        "configurable": {"thread_id": "proj_targeted"},
        "recursion_limit": 50,
    }

    result = await graph.ainvoke(create_initial_state("proj_targeted", _brief()), config)
    result = await graph.ainvoke(
        Command(resume=_decision(_request(result), DecisionAction.APPROVE)), config
    )
    scenario_request = _request(result)
    result = await graph.ainvoke(
        Command(
            resume=_decision(
                scenario_request,
                DecisionAction.RESEARCH_MORE,
                affected=["task_proj_targeted_user"],
            )
        ),
        config,
    )

    assert _request(result).gate is GateName.SCENARIO
    assert runtime.call_counts[ResearchAgentType.USER_RESEARCH] == 2
    assert runtime.call_counts[ResearchAgentType.COMPETITOR_RESEARCH] == 1
    skipped = [
        event
        for event in result["node_history"]
        if event["event_type"] == "agent_node_skipped"
    ]
    assert skipped[-1]["task_id"] == "task_proj_targeted_competitor"


@pytest.mark.asyncio
async def test_runner_exposes_checkpoint_without_leaking_langgraph_call_details() -> None:
    runtime = TestAgentRuntime()
    runner = WorkflowRunner(compile_research_graph(runtime, InMemorySaver()))

    result = await runner.start(create_initial_state("proj_runner", _brief()))
    snapshot = await runner.snapshot("proj_runner")

    assert _request(result).gate is GateName.BRIEF
    assert snapshot.thread_id == "proj_runner"
    assert snapshot.checkpoint_id is not None
    assert snapshot.next_nodes == ["brief_gate"]
    assert snapshot.values["pending_gate"]["gate"] == "brief"
