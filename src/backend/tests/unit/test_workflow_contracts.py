from copy import deepcopy

import pytest

from app.schemas.project import DecisionAction, ResearchBrief
from app.workflows.context import build_agent_context
from app.workflows.contracts import (
    AgentContext,
    GateName,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
    StageDecision,
    WorkflowContractError,
)
from app.workflows.gates import build_gate_request, validate_stage_decision
from app.workflows.graph import create_initial_state
from app.workflows.planning import PLANNED_AGENT_TYPES, parse_task_plan
from app.workflows.runtime import AgentRuntimeNotBoundError, UnboundAgentRuntime
from tests.integration.workflow_runtime import TestAgentRuntime
from tests.research_brief import home_safety_brief


def _brief() -> ResearchBrief:
    return home_safety_brief()


@pytest.mark.asyncio
async def test_unbound_runtime_fails_instead_of_generating_placeholder() -> None:
    runtime = UnboundAgentRuntime()
    task = ResearchTask(
        task_id="task_user",
        project_id="proj_test",
        agent_type=ResearchAgentType.USER_RESEARCH,
        goal="research users",
    )
    with pytest.raises(AgentRuntimeNotBoundError, match="AGENT_RUNTIME_NOT_BOUND"):
        await runtime.execute(
            task,
            build_agent_context(create_initial_state("proj_test", _brief()), task.agent_type),
        )


@pytest.mark.asyncio
async def test_manager_plan_requires_all_roles_and_dependencies() -> None:
    runtime = TestAgentRuntime()
    state = create_initial_state("proj_test", _brief())
    task = ResearchTask(
        task_id="task_plan",
        project_id="proj_test",
        agent_type=ResearchAgentType.RESEARCH_MANAGER,
        goal="plan",
    )
    artifact = await runtime.execute(
        task,
        AgentContext(project_id="proj_test", brief=_brief(), iteration=0),
    )

    tasks = parse_task_plan(artifact, "proj_test")
    # 当前主路径只规划已经接线的用户、竞品生态与生态机会 Agent。
    assert {item.agent_type for item in tasks} == set(PLANNED_AGENT_TYPES)

    invalid_payload = deepcopy(artifact.model_dump(mode="json"))
    invalid_payload["payload"]["tasks"] = invalid_payload["payload"]["tasks"][:-1]
    with pytest.raises(WorkflowContractError, match="role mismatch"):
        parse_task_plan(ResearchArtifact.model_validate(invalid_payload), "proj_test")
    assert state["task_plan"] == []


def test_context_builder_exposes_only_allowed_upstream_artifacts() -> None:
    state = create_initial_state("proj_test", _brief())
    state["artifacts"] = {
        agent.value: ResearchArtifact(
            artifact_id=f"artifact_{agent}",
            task_id=f"task_{agent}",
            artifact_type=agent,
            status=ResearchTaskStatus.COMPLETED,
            quality_score=90,
        ).model_dump(mode="json")
        for agent in ResearchAgentType
    }

    user_context = build_agent_context(state, ResearchAgentType.USER_RESEARCH)
    commercial_context = build_agent_context(state, ResearchAgentType.COMMERCIAL_EVALUATION)
    ecosystem_context = build_agent_context(state, ResearchAgentType.ECOSYSTEM_OPPORTUNITY)
    technical_context = build_agent_context(state, ResearchAgentType.TECHNICAL_FEASIBILITY)
    policy_context = build_agent_context(state, ResearchAgentType.SECURITY_POLICY)

    assert user_context.upstream_artifacts == {}
    assert set(commercial_context.upstream_artifacts) == {
        "user_research",
        "competitor_research",
        "ecosystem_opportunity",
        "technical_feasibility",
    }
    assert "red_team" not in commercial_context.upstream_artifacts
    assert set(ecosystem_context.upstream_artifacts) == {
        "user_research",
        "competitor_research",
    }
    assert set(technical_context.upstream_artifacts) == {"ecosystem_opportunity"}
    assert set(policy_context.upstream_artifacts) == {
        "ecosystem_opportunity",
        "technical_feasibility",
        "security_policy",
    }


def test_gate_rejects_wrong_id_and_scenario_approval_without_selection() -> None:
    request = build_gate_request("proj_test", GateName.SCENARIO, 0, {})
    wrong = StageDecision(
        decision_id="decision_wrong",
        gate=GateName.SCENARIO,
        action=DecisionAction.APPROVE,
        actor="tester",
        reason="wrong id",
        selected_innovation_ids=["inv_one"],
    )
    with pytest.raises(WorkflowContractError, match="decision id"):
        validate_stage_decision(wrong, request)

    no_selection = wrong.model_copy(update={"decision_id": request.decision_id})
    no_selection.selected_innovation_ids = []
    with pytest.raises(WorkflowContractError, match="select at least one"):
        validate_stage_decision(no_selection, request)


def test_ai_native_gate_only_approves_deterministically_eligible_opportunities() -> None:
    request = build_gate_request(
        "proj_test",
        GateName.AI_NATIVE_ECOSYSTEM,
        0,
        {
            "eligible_opportunity_ids": ["eco_allowed"],
            "source_recovery_gap_ids": [],
        },
    )
    assert DecisionAction.RESEARCH_MORE not in request.allowed_actions
    invalid = StageDecision(
        decision_id=request.decision_id,
        gate=request.gate,
        action=DecisionAction.APPROVE,
        actor="tester",
        reason="select a blocked candidate",
        selected_innovation_ids=["eco_blocked"],
    )
    with pytest.raises(WorkflowContractError, match="did not pass"):
        validate_stage_decision(invalid, request)
