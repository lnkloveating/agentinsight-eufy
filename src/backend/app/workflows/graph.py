"""AgentInsight 产品研究主图：编排、门禁、有限返工和 Checkpoint。"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.schemas.project import DecisionAction, ResearchBrief
from app.workflows.context import build_agent_context
from app.workflows.contracts import (
    GateName,
    GateRequest,
    ResearchAgentType,
    ResearchArtifact,
    ResearchBudget,
    ResearchState,
    ResearchTask,
    ResearchTaskStatus,
    WorkflowContractError,
    WorkflowEvent,
    WorkflowNodeError,
    WorkflowOutcome,
)
from app.workflows.gates import (
    build_gate_request,
    evaluate_research_artifacts,
    parse_red_team_directive,
    summarize_artifacts,
    validate_stage_decision,
)
from app.workflows.planning import parse_task_plan, task_for_agent
from app.workflows.runtime import AgentRuntime

CompiledResearchGraph = CompiledStateGraph[
    ResearchState,
    None,
    ResearchState,
    ResearchState,
]


def create_initial_state(
    project_id: str,
    brief: ResearchBrief,
    *,
    max_iterations: int = 2,
) -> ResearchState:
    if max_iterations < 0:
        raise ValueError("max_iterations cannot be negative")
    return ResearchState(
        project_id=project_id,
        brief=brief.model_dump(mode="json"),
        outcome=WorkflowOutcome.RUNNING.value,
        current_stage="brief_confirmation",
        progress=5,
        task_plan=[],
        artifacts={},
        iteration=0,
        max_iterations=max_iterations,
        affected_task_ids=[],
        selected_innovation_ids=[],
        pending_gate=None,
        decision_history=[],
        node_history=[],
        terminal_reason=None,
    )


class ResearchWorkflow:
    """使用注入式 Runtime 构建可测试、可恢复但不绑定模型的完整主图。"""

    def __init__(
        self,
        runtime: AgentRuntime,
        checkpointer: BaseCheckpointSaver[Any],
    ) -> None:
        self.runtime = runtime
        self.graph = self._build(checkpointer)

    def _build(self, checkpointer: BaseCheckpointSaver[Any]) -> CompiledResearchGraph:
        builder = StateGraph(ResearchState)
        builder.add_node("prepare_brief_gate", self._prepare_brief_gate)
        builder.add_node("brief_gate", self._brief_gate)
        builder.add_node("research_planner", self._research_planner)
        builder.add_node("user_research", self._user_research)
        builder.add_node("competitor_research", self._competitor_research)
        builder.add_node("evidence_readiness_gate", self._evidence_readiness_gate)
        builder.add_node("prepare_research_revision", self._prepare_research_revision)
        builder.add_node("product_technical", self._product_technical)
        builder.add_node("commercial_evaluation", self._commercial_evaluation)
        builder.add_node("red_team", self._red_team)
        builder.add_node("red_team_router", self._red_team_router)
        builder.add_node("prepare_product_revision", self._prepare_product_revision)
        builder.add_node("candidate_synthesis", self._candidate_synthesis)
        builder.add_node("prepare_scenario_gate", self._prepare_scenario_gate)
        builder.add_node("scenario_gate", self._scenario_gate)
        builder.add_node("validation_dispatch", self._validation_dispatch)
        builder.add_node("prepare_validation_revision", self._prepare_validation_revision)
        builder.add_node("final_synthesis", self._final_synthesis)
        builder.add_node("prepare_final_gate", self._prepare_final_gate)
        builder.add_node("final_gate", self._final_gate)
        builder.add_node("complete", self._complete)
        builder.add_node("reject", self._reject)
        builder.add_node("terminate", self._terminate)
        builder.add_node("inconclusive", self._inconclusive)
        builder.add_node("brief_revision", self._brief_revision)

        builder.add_edge(START, "prepare_brief_gate")
        builder.add_edge("prepare_brief_gate", "brief_gate")
        builder.add_conditional_edges(
            "brief_gate",
            self._route_brief_decision,
            {
                "approve": "research_planner",
                "revise": "brief_revision",
                "terminate": "terminate",
            },
        )
        builder.add_edge("research_planner", "user_research")
        builder.add_edge("research_planner", "competitor_research")
        builder.add_edge(
            ["user_research", "competitor_research"],
            "evidence_readiness_gate",
        )
        builder.add_conditional_edges(
            "evidence_readiness_gate",
            self._route_evidence_gate,
            {
                "pass": "product_technical",
                "retry": "prepare_research_revision",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("prepare_research_revision", "user_research")
        builder.add_edge("prepare_research_revision", "competitor_research")
        builder.add_edge("product_technical", "commercial_evaluation")
        builder.add_edge("commercial_evaluation", "red_team")
        builder.add_edge("red_team", "red_team_router")
        builder.add_conditional_edges(
            "red_team_router",
            self._route_red_team,
            {
                "synthesize": "candidate_synthesis",
                "research_more": "prepare_research_revision",
                "revise": "prepare_product_revision",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("prepare_product_revision", "product_technical")
        builder.add_edge("candidate_synthesis", "prepare_scenario_gate")
        builder.add_edge("prepare_scenario_gate", "scenario_gate")
        builder.add_conditional_edges(
            "scenario_gate",
            self._route_scenario_decision,
            {
                "approve": "validation_dispatch",
                "research_more": "prepare_research_revision",
                "revise": "prepare_product_revision",
                "reject": "reject",
                "terminate": "terminate",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("validation_dispatch", "final_synthesis")
        builder.add_edge("prepare_validation_revision", "validation_dispatch")
        builder.add_edge("final_synthesis", "prepare_final_gate")
        builder.add_edge("prepare_final_gate", "final_gate")
        builder.add_conditional_edges(
            "final_gate",
            self._route_final_decision,
            {
                "approve": "complete",
                "research_more": "prepare_research_revision",
                "revise": "prepare_validation_revision",
                "reject": "reject",
                "terminate": "terminate",
                "inconclusive": "inconclusive",
            },
        )
        for terminal_node in (
            "complete",
            "reject",
            "terminate",
            "inconclusive",
            "brief_revision",
        ):
            builder.add_edge(terminal_node, END)
        return builder.compile(checkpointer=checkpointer, name="agentinsight_research")

    async def _prepare_brief_gate(self, state: ResearchState) -> dict[str, Any]:
        return self._prepare_gate(
            state,
            GateName.BRIEF,
            {"brief": state["brief"]},
            "brief_confirmation",
            5,
        )

    async def _brief_gate(self, state: ResearchState) -> dict[str, Any]:
        return self._handle_gate(state, GateName.BRIEF)

    async def _research_planner(self, state: ResearchState) -> dict[str, Any]:
        task = ResearchTask(
            task_id=f"task_{state['project_id']}_plan",
            project_id=state["project_id"],
            agent_type=ResearchAgentType.RESEARCH_MANAGER,
            goal="生成结构化研究计划、依赖、预算和验收条件。",
            required_artifacts=["research_task_plan"],
            budget=ResearchBudget(max_iterations=state.get("max_iterations", 2)),
            acceptance_checks=["all_required_roles", "valid_dependencies"],
        )
        artifact = await self._execute(state, task, "research_planner")
        tasks = parse_task_plan(artifact, state["project_id"])
        return {
            "task_plan": [item.model_dump(mode="json") for item in tasks],
            "artifacts": {ResearchAgentType.RESEARCH_MANAGER: artifact.model_dump(mode="json")},
            "current_stage": "parallel_research",
            "progress": 15,
            "node_history": [self._event("research_planner", task, "completed")],
        }

    async def _user_research(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state, ResearchAgentType.USER_RESEARCH, "user_research", 30, allow_partial=True
        )

    async def _competitor_research(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state,
            ResearchAgentType.COMPETITOR_RESEARCH,
            "competitor_research_a2a",
            30,
            allow_partial=True,
        )

    async def _evidence_readiness_gate(self, state: ResearchState) -> dict[str, Any]:
        artifacts = {
            key: ResearchArtifact.model_validate(value)
            for key, value in state.get("artifacts", {}).items()
        }
        result = evaluate_research_artifacts(artifacts)
        return {
            "evidence_gate": result.model_dump(mode="json"),
            "affected_task_ids": self._research_task_ids(state) if not result.passed else [],
            "current_stage": "evidence_readiness_gate",
            "progress": 40,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_gate_evaluated",
                    node="evidence_readiness_gate",
                    status="passed" if result.passed else "needs_research",
                    message="研究 Artifact 已就绪。" if result.passed else ";".join(result.issues),
                ).model_dump(mode="json")
            ],
        }

    async def _prepare_research_revision(self, state: ResearchState) -> dict[str, Any]:
        return self._prepare_revision(state, "targeted_research", self._research_task_ids(state))

    async def _product_technical(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state, ResearchAgentType.PRODUCT_TECHNICAL, "product_technical", 50
        )

    async def _commercial_evaluation(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state, ResearchAgentType.COMMERCIAL_EVALUATION, "commercial_evaluation", 60
        )

    async def _red_team(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(state, ResearchAgentType.RED_TEAM, "red_team", 68)

    async def _red_team_router(self, state: ResearchState) -> dict[str, Any]:
        artifact = self._artifact(state, ResearchAgentType.RED_TEAM)
        directive = parse_red_team_directive(artifact)
        return {
            "routing_decision": directive.decision,
            "affected_task_ids": directive.affected_task_ids,
            "node_history": [
                WorkflowEvent(
                    event_type="red_team_routed",
                    node="red_team_router",
                    task_id=artifact.task_id,
                    status=directive.decision,
                    message="红队决定已进入确定性路由。",
                ).model_dump(mode="json")
            ],
        }

    async def _prepare_product_revision(self, state: ResearchState) -> dict[str, Any]:
        product_task = self._task(state, ResearchAgentType.PRODUCT_TECHNICAL)
        return self._prepare_revision(state, "product_revision", [product_task.task_id])

    async def _candidate_synthesis(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state, ResearchAgentType.CANDIDATE_SYNTHESIS, "candidate_synthesis", 72
        )

    async def _prepare_scenario_gate(self, state: ResearchState) -> dict[str, Any]:
        artifacts = [
            self._artifact(state, ResearchAgentType.CANDIDATE_SYNTHESIS),
            self._artifact(state, ResearchAgentType.RED_TEAM),
        ]
        return self._prepare_gate(
            state,
            GateName.SCENARIO,
            summarize_artifacts(artifacts),
            "scenario_approval",
            75,
        )

    async def _scenario_gate(self, state: ResearchState) -> dict[str, Any]:
        return self._handle_gate(state, GateName.SCENARIO)

    async def _validation_dispatch(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state, ResearchAgentType.VALIDATION, "validation_dispatch", 82
        )

    async def _prepare_validation_revision(self, state: ResearchState) -> dict[str, Any]:
        task = self._task(state, ResearchAgentType.VALIDATION)
        return self._prepare_revision(state, "validation_revision", [task.task_id])

    async def _final_synthesis(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state, ResearchAgentType.FINAL_SYNTHESIS, "final_synthesis", 90
        )

    async def _prepare_final_gate(self, state: ResearchState) -> dict[str, Any]:
        artifacts = [
            self._artifact(state, ResearchAgentType.FINAL_SYNTHESIS),
            self._artifact(state, ResearchAgentType.VALIDATION),
        ]
        return self._prepare_gate(
            state,
            GateName.FINAL,
            summarize_artifacts(artifacts),
            "final_approval",
            95,
        )

    async def _final_gate(self, state: ResearchState) -> dict[str, Any]:
        return self._handle_gate(state, GateName.FINAL)

    async def _complete(self, state: ResearchState) -> dict[str, Any]:
        return self._terminal(state, WorkflowOutcome.COMPLETED, "final_approved", 100)

    async def _reject(self, state: ResearchState) -> dict[str, Any]:
        return self._terminal(state, WorkflowOutcome.REJECTED, "not_recommended", 100)

    async def _terminate(self, state: ResearchState) -> dict[str, Any]:
        return self._terminal(state, WorkflowOutcome.TERMINATED, "user_terminated", 100)

    async def _inconclusive(self, state: ResearchState) -> dict[str, Any]:
        return self._terminal(
            state,
            WorkflowOutcome.INCONCLUSIVE,
            "research_budget_exhausted_or_evidence_insufficient",
            100,
        )

    async def _brief_revision(self, state: ResearchState) -> dict[str, Any]:
        return self._terminal(
            state,
            WorkflowOutcome.INCONCLUSIVE,
            "brief_revision_requested",
            5,
        )

    async def _run_planned_agent(
        self,
        state: ResearchState,
        agent_type: ResearchAgentType,
        stage: str,
        progress: int,
        *,
        allow_partial: bool = False,
    ) -> dict[str, Any]:
        task = self._task(state, agent_type)
        affected = state.get("affected_task_ids", [])
        if (
            affected
            and task.task_id not in affected
            and agent_type
            in {
                ResearchAgentType.USER_RESEARCH,
                ResearchAgentType.COMPETITOR_RESEARCH,
            }
        ):
            update: dict[str, Any] = {
                "node_history": [self._event(stage, task, "skipped")],
            }
            return update
        artifact = await self._execute(state, task, stage)
        accepted = {ResearchTaskStatus.COMPLETED}
        if allow_partial:
            accepted.add(ResearchTaskStatus.PARTIAL)
        if artifact.status not in accepted:
            raise WorkflowContractError(
                f"{agent_type} returned non-advancing status {artifact.status}"
            )
        update = {
            "artifacts": {agent_type: artifact.model_dump(mode="json")},
            "node_history": [self._event(stage, task, artifact.status)],
        }
        if agent_type not in {
            ResearchAgentType.USER_RESEARCH,
            ResearchAgentType.COMPETITOR_RESEARCH,
        }:
            update["current_stage"] = stage
            update["progress"] = progress
        return update

    async def _execute(
        self,
        state: ResearchState,
        task: ResearchTask,
        node: str,
    ) -> ResearchArtifact:
        try:
            artifact = await self.runtime.execute(
                task,
                build_agent_context(state, task.agent_type),
            )
        except Exception as exc:
            raise WorkflowNodeError(node, task.task_id, exc) from exc
        if artifact.task_id != task.task_id:
            raise WorkflowContractError(
                f"artifact task id {artifact.task_id} does not match {task.task_id}"
            )
        if artifact.artifact_type != task.agent_type:
            raise WorkflowContractError(
                f"artifact type {artifact.artifact_type} does not match {task.agent_type}"
            )
        return artifact

    def _prepare_gate(
        self,
        state: ResearchState,
        gate: GateName,
        summary: dict[str, object],
        stage: str,
        progress: int,
    ) -> dict[str, Any]:
        request = build_gate_request(state["project_id"], gate, state.get("iteration", 0), summary)
        return {
            "pending_gate": request.model_dump(mode="json"),
            "outcome": WorkflowOutcome.AWAITING_DECISION.value,
            "current_stage": stage,
            "progress": progress,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_gate_pending",
                    node=f"{gate}_gate",
                    status="waiting",
                    message=f"等待 {gate} 人工决定。",
                ).model_dump(mode="json")
            ],
        }

    def _handle_gate(self, state: ResearchState, gate: GateName) -> dict[str, Any]:
        pending = state.get("pending_gate")
        if pending is None:
            raise WorkflowContractError(f"{gate} gate has no pending request")
        request = GateRequest.model_validate(pending)
        raw_decision = interrupt(request.model_dump(mode="json"))
        decision = validate_stage_decision(raw_decision, request)
        return {
            "pending_gate": None,
            "outcome": WorkflowOutcome.RUNNING.value,
            "routing_decision": decision.action.value,
            "selected_innovation_ids": (
                decision.selected_innovation_ids
                if decision.selected_innovation_ids
                else state.get("selected_innovation_ids", [])
            ),
            "affected_task_ids": decision.affected_task_ids,
            "decision_history": [decision.model_dump(mode="json")],
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_gate_decided",
                    node=f"{gate}_gate",
                    status=decision.action,
                    message=decision.reason,
                ).model_dump(mode="json")
            ],
        }

    def _prepare_revision(
        self,
        state: ResearchState,
        stage: str,
        default_task_ids: list[str],
    ) -> dict[str, Any]:
        affected = state.get("affected_task_ids", []) or default_task_ids
        return {
            "iteration": state.get("iteration", 0) + 1,
            "affected_task_ids": affected,
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": stage,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_revision_started",
                    node=stage,
                    status="running",
                    message=f"只重跑受影响任务：{','.join(affected)}",
                ).model_dump(mode="json")
            ],
        }

    def _terminal(
        self,
        state: ResearchState,
        outcome: WorkflowOutcome,
        reason: str,
        progress: int,
    ) -> dict[str, Any]:
        del state
        return {
            "outcome": outcome.value,
            "current_stage": outcome.value,
            "progress": progress,
            "terminal_reason": reason,
            "pending_gate": None,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_finished",
                    node=outcome.value,
                    status=outcome.value,
                    message=reason,
                ).model_dump(mode="json")
            ],
        }

    @staticmethod
    def _route_brief_decision(state: ResearchState) -> str:
        return state["routing_decision"]

    @staticmethod
    def _route_evidence_gate(state: ResearchState) -> str:
        result = state.get("evidence_gate", {})
        if bool(result.get("passed")):
            return "pass"
        if state.get("iteration", 0) >= state.get("max_iterations", 2):
            return "inconclusive"
        return "retry"

    @staticmethod
    def _route_red_team(state: ResearchState) -> str:
        decision = state["routing_decision"]
        if decision in {"pass", "reject"}:
            return "synthesize"
        if state.get("iteration", 0) >= state.get("max_iterations", 2):
            return "inconclusive"
        return decision

    @staticmethod
    def _route_scenario_decision(state: ResearchState) -> str:
        return ResearchWorkflow._route_gate_rework(state)

    @staticmethod
    def _route_final_decision(state: ResearchState) -> str:
        return ResearchWorkflow._route_gate_rework(state)

    @staticmethod
    def _route_gate_rework(state: ResearchState) -> str:
        decision = state["routing_decision"]
        if decision in {DecisionAction.RESEARCH_MORE, DecisionAction.REVISE} and state.get(
            "iteration", 0
        ) >= state.get("max_iterations", 2):
            return "inconclusive"
        return decision

    @staticmethod
    def _event(
        node: str,
        task: ResearchTask,
        status: str | ResearchTaskStatus,
    ) -> dict[str, Any]:
        return WorkflowEvent(
            event_type="agent_node_completed" if status != "skipped" else "agent_node_skipped",
            node=node,
            task_id=task.task_id,
            status=str(status),
            message=f"{task.agent_type} 节点状态：{status}",
        ).model_dump(mode="json")

    @staticmethod
    def _task_plan(state: ResearchState) -> list[ResearchTask]:
        return [ResearchTask.model_validate(item) for item in state.get("task_plan", [])]

    def _task(self, state: ResearchState, agent_type: ResearchAgentType) -> ResearchTask:
        return task_for_agent(self._task_plan(state), agent_type)

    def _research_task_ids(self, state: ResearchState) -> list[str]:
        return [
            self._task(state, ResearchAgentType.USER_RESEARCH).task_id,
            self._task(state, ResearchAgentType.COMPETITOR_RESEARCH).task_id,
        ]

    @staticmethod
    def _artifact(state: ResearchState, agent_type: ResearchAgentType) -> ResearchArtifact:
        raw = state.get("artifacts", {}).get(agent_type)
        if raw is None:
            raise WorkflowContractError(f"missing artifact for {agent_type}")
        return ResearchArtifact.model_validate(raw)


def compile_research_graph(
    runtime: AgentRuntime,
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledResearchGraph:
    return ResearchWorkflow(runtime, checkpointer).graph
