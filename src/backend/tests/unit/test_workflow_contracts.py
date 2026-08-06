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
from app.workflows.planning import parse_task_plan
from app.workflows.runtime import AgentRuntimeNotBoundError, UnboundAgentRuntime
from tests.integration.workflow_runtime import TestAgentRuntime


def _brief() -> ResearchBrief:
    return ResearchBrief(
        question="北美家庭安防中有哪些值得验证的事件理解机会？",
        category="家庭安防",
        target_user="北美家庭安防用户",
        region="北美",
    )


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
    assert {item.agent_type for item in tasks} == set(ResearchAgentType) - {
        ResearchAgentType.RESEARCH_MANAGER
    }

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

    assert user_context.upstream_artifacts == {}
    assert set(commercial_context.upstream_artifacts) == {
        "user_research",
        "competitor_research",
        "product_technical",
    }
    assert "red_team" not in commercial_context.upstream_artifacts


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
