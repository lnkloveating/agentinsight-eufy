"""AgentInsight 产品研究主图：编排、门禁、有限返工和 Checkpoint。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.schemas.project import DecisionAction, ResearchBrief
from app.schemas.source_recovery import SourceRecovery
from app.workflows.ai_native_gate import (
    AINativeEcosystemGate,
    AINativeEcosystemGateResult,
)
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
    WorkflowSourceRecoveryRequest,
)
from app.workflows.gates import (
    build_gate_request,
    evaluate_research_artifacts,
    validate_stage_decision,
)
from app.workflows.handoff import affected_research_agents, build_research_handoff
from app.workflows.planning import parse_task_plan, task_for_agent
from app.workflows.runtime import AgentRuntime
from app.workflows.source_recovery import prepare_source_recovery_resume

if TYPE_CHECKING:
    from app.agents.red_team_policy_revision.contracts import RedTeamArtifact

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
        ai_native_gate={},
        research_handoff=None,
        iteration=0,
        max_iterations=max_iterations,
        affected_task_ids=[],
        selected_innovation_ids=[],
        pending_gate=None,
        pending_source_recovery=None,
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
        builder.add_node("ecosystem_opportunity", self._ecosystem_opportunity)
        builder.add_node("evaluate_ai_native_gate", self._evaluate_ai_native_gate)
        builder.add_node("prepare_ai_native_gate", self._prepare_ai_native_gate)
        builder.add_node("ai_native_gate", self._ai_native_gate)
        builder.add_node("prepare_ecosystem_revision", self._prepare_ecosystem_revision)
        builder.add_node("prepare_source_recovery", self._prepare_source_recovery)
        builder.add_node("source_recovery_gate", self._source_recovery_gate)
        builder.add_node("prepare_technical_feasibility", self._prepare_technical_feasibility)
        builder.add_node("technical_feasibility", self._technical_feasibility)
        builder.add_node(
            "prepare_technical_source_recovery",
            self._prepare_technical_source_recovery,
        )
        builder.add_node(
            "technical_source_recovery_gate",
            self._technical_source_recovery_gate,
        )
        builder.add_node("prepare_security_policy", self._prepare_security_policy)
        builder.add_node("security_policy", self._security_policy)
        builder.add_node("prepare_policy_verification", self._prepare_policy_verification)
        builder.add_node("policy_verification", self._policy_verification)
        builder.add_node("policy_verification_complete", self._policy_verification_complete)
        builder.add_node("prepare_commercial_evaluation", self._prepare_commercial_evaluation)
        builder.add_node("commercial_evaluation", self._commercial_evaluation)
        builder.add_node(
            "prepare_commercial_source_recovery",
            self._prepare_commercial_source_recovery,
        )
        builder.add_node(
            "commercial_source_recovery_gate",
            self._commercial_source_recovery_gate,
        )
        builder.add_node("commercial_complete", self._commercial_complete)
        builder.add_node("prepare_red_team", self._prepare_red_team)
        builder.add_node("red_team", self._red_team)
        builder.add_node(
            "prepare_red_team_source_recovery",
            self._prepare_red_team_source_recovery,
        )
        builder.add_node(
            "red_team_source_recovery_gate",
            self._red_team_source_recovery_gate,
        )
        builder.add_node("prepare_red_team_revision", self._prepare_red_team_revision)
        builder.add_node("red_team_revision_dispatch", self._red_team_revision_dispatch)
        builder.add_node("red_team_research_revision", self._red_team_research_revision)
        builder.add_node("red_team_complete", self._red_team_complete)
        builder.add_node("red_team_human_review", self._red_team_human_review)
        builder.add_node("red_team_rejected", self._red_team_rejected)
        builder.add_node("awaiting_policy_revision", self._awaiting_policy_revision)
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
                "pass": "ecosystem_opportunity",
                "retry": "prepare_research_revision",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("prepare_research_revision", "user_research")
        builder.add_edge("prepare_research_revision", "competitor_research")
        builder.add_edge("ecosystem_opportunity", "evaluate_ai_native_gate")
        builder.add_edge("evaluate_ai_native_gate", "prepare_ai_native_gate")
        builder.add_edge("prepare_ai_native_gate", "ai_native_gate")
        builder.add_conditional_edges(
            "ai_native_gate",
            self._route_ai_native_decision,
            {
                "approve": "prepare_technical_feasibility",
                "research_more": "prepare_source_recovery",
                "revise": "prepare_ecosystem_revision",
                "reject": "reject",
                "terminate": "terminate",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("prepare_ecosystem_revision", "ecosystem_opportunity")
        builder.add_edge("prepare_source_recovery", "source_recovery_gate")
        builder.add_edge("source_recovery_gate", "ecosystem_opportunity")
        builder.add_edge("prepare_technical_feasibility", "technical_feasibility")
        builder.add_conditional_edges(
            "technical_feasibility",
            self._route_technical_feasibility,
            {
                "advance": "prepare_security_policy",
                "research_more": "prepare_technical_source_recovery",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge(
            "prepare_technical_source_recovery",
            "technical_source_recovery_gate",
        )
        builder.add_edge("technical_source_recovery_gate", "technical_feasibility")
        builder.add_edge("prepare_security_policy", "security_policy")
        builder.add_edge("security_policy", "prepare_policy_verification")
        builder.add_edge("prepare_policy_verification", "policy_verification")
        builder.add_edge("policy_verification", "policy_verification_complete")
        builder.add_conditional_edges(
            "policy_verification_complete",
            self._route_policy_verification_complete,
            {
                "advance": "prepare_commercial_evaluation",
                "revision": "awaiting_policy_revision",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("prepare_commercial_evaluation", "commercial_evaluation")
        builder.add_conditional_edges(
            "commercial_evaluation",
            self._route_commercial_evaluation,
            {
                "advance": "commercial_complete",
                "research_more": "prepare_commercial_source_recovery",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("prepare_commercial_source_recovery", "commercial_source_recovery_gate")
        builder.add_edge("commercial_source_recovery_gate", "commercial_evaluation")
        builder.add_edge("commercial_complete", "prepare_red_team")
        builder.add_edge("prepare_red_team", "red_team")
        builder.add_conditional_edges(
            "red_team",
            self._route_red_team,
            {
                "pass": "red_team_complete",
                "revise": "prepare_red_team_revision",
                "needs_more_evidence": "prepare_red_team_source_recovery",
                "human_review": "red_team_human_review",
                "reject": "red_team_rejected",
                "inconclusive": "inconclusive",
            },
        )
        builder.add_edge("prepare_red_team_source_recovery", "red_team_source_recovery_gate")
        builder.add_edge("red_team_source_recovery_gate", "red_team")
        builder.add_edge("prepare_red_team_revision", "red_team_revision_dispatch")
        builder.add_conditional_edges(
            "red_team_revision_dispatch",
            self._route_red_team_revision,
            {
                "research": "red_team_research_revision",
                "ecosystem_opportunity": "ecosystem_opportunity",
                "technical_feasibility": "prepare_technical_feasibility",
                "security_policy": "prepare_security_policy",
                "policy_verification": "prepare_policy_verification",
                "commercial_evaluation": "prepare_commercial_evaluation",
            },
        )
        builder.add_edge("red_team_research_revision", "user_research")
        builder.add_edge("red_team_research_revision", "competitor_research")
        for terminal_node in (
            "red_team_complete",
            "red_team_human_review",
            "red_team_rejected",
            "awaiting_policy_revision",
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
        handoff = build_research_handoff(artifacts)
        result = evaluate_research_artifacts(artifacts)
        affected_agents = affected_research_agents(handoff)
        affected_task_ids = [
            self._task(state, agent_type).task_id
            for agent_type in sorted(affected_agents, key=lambda item: item.value)
        ]
        return {
            "evidence_gate": result.model_dump(mode="json"),
            "research_handoff": handoff.model_dump(mode="json"),
            "affected_task_ids": affected_task_ids if not result.passed else [],
            "current_stage": "evidence_readiness_gate",
            "progress": 40,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_research_handoff_evaluated",
                    node="evidence_readiness_gate",
                    status=handoff.status,
                    message=(
                        "研究结果已交接给产品技术阶段。"
                        if result.passed
                        else ";".join(result.issues)
                    ),
                ).model_dump(mode="json")
            ],
        }

    async def _prepare_commercial_evaluation(self, state: ResearchState) -> dict[str, Any]:
        verification_task = self._task(state, ResearchAgentType.POLICY_VERIFICATION)
        selected_ids = list(dict.fromkeys(state.get("selected_innovation_ids", [])))
        task = ResearchTask(
            task_id=f"task_{state['project_id']}_commercial_evaluation_v2",
            project_id=state["project_id"],
            agent_type=ResearchAgentType.COMMERCIAL_EVALUATION,
            goal=(
                "Evaluate user value, business hypotheses and delivery conditions without scoring."
            ),
            scope={"opportunity_ids": selected_ids},
            required_artifacts=[
                ResearchAgentType.USER_RESEARCH.value,
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
                ResearchAgentType.TECHNICAL_FEASIBILITY.value,
                ResearchAgentType.POLICY_VERIFICATION.value,
            ],
            evidence_rules=verification_task.evidence_rules,
            budget=ResearchBudget(
                max_pages=verification_task.budget.max_pages,
                max_iterations=state.get("max_iterations", 2),
                deadline_seconds=180,
            ),
            depends_on=[verification_task.task_id],
            acceptance_checks=[
                "user_value_evidence_bound",
                "business_claims_evidence_bound",
                "delivery_uses_upstream_verdicts",
                "no_weighted_score",
            ],
        )
        plan = self._task_plan(state)
        plan = [item for item in plan if item.agent_type is not task.agent_type]
        plan.append(task)
        return {
            "task_plan": [item.model_dump(mode="json") for item in plan],
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": "commercial_evaluation_preparation",
            "progress": 89,
            "node_history": [self._event("prepare_commercial_evaluation", task, "prepared")],
        }

    async def _commercial_evaluation(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state,
            ResearchAgentType.COMMERCIAL_EVALUATION,
            "commercial_evaluation_v2",
            93,
            accepted_statuses={ResearchTaskStatus.COMPLETED, ResearchTaskStatus.PARTIAL},
        )

    async def _prepare_commercial_source_recovery(self, state: ResearchState) -> dict[str, Any]:
        artifact = self._artifact(state, ResearchAgentType.COMMERCIAL_EVALUATION)
        gaps = artifact.payload.get("commercial_gaps", [])
        gap_ids = [
            str(item["gap_id"]) for item in gaps if isinstance(item, dict) and item.get("gap_id")
        ]
        questions = [
            str(item["question"])
            for item in gaps
            if isinstance(item, dict) and item.get("question")
        ]
        if not gap_ids or not questions:
            raise WorkflowContractError(
                "needs_more_evidence commercial result requires explicit gaps"
            )
        request = WorkflowSourceRecoveryRequest(
            project_id=state["project_id"],
            source_artifact_id=artifact.artifact_id,
            source_task_id=artifact.task_id,
            gap_ids=list(dict.fromkeys(gap_ids))[:50],
            questions=list(dict.fromkeys(questions))[:50],
            affected_agent_types=[ResearchAgentType.COMMERCIAL_EVALUATION.value],
        )
        return {
            "pending_source_recovery": request.model_dump(mode="json"),
            "outcome": WorkflowOutcome.AWAITING_SOURCE_RECOVERY.value,
            "current_stage": "commercial_source_recovery",
            "progress": 93,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_source_recovery_pending",
                    node="prepare_commercial_source_recovery",
                    task_id=artifact.task_id,
                    status="waiting",
                    message="等待补充销量、成本、支持、合规或付费意愿证据。",
                ).model_dump(mode="json")
            ],
        }

    async def _commercial_source_recovery_gate(self, state: ResearchState) -> dict[str, Any]:
        pending = state.get("pending_source_recovery")
        if pending is None:
            raise WorkflowContractError("commercial source recovery has no pending request")
        request = WorkflowSourceRecoveryRequest.model_validate(pending)
        recovery = SourceRecovery.model_validate(interrupt(request.model_dump(mode="json")))
        update = prepare_source_recovery_resume(state, recovery)
        task = self._task(state, ResearchAgentType.COMMERCIAL_EVALUATION)
        if task.task_id not in update["affected_task_ids"]:
            raise WorkflowContractError(
                "source recovery does not target commercial evaluation task"
            )
        return {
            **update,
            "pending_source_recovery": None,
            "outcome": WorkflowOutcome.RUNNING.value,
        }

    async def _commercial_complete(self, state: ResearchState) -> dict[str, Any]:
        artifact = self._artifact(state, ResearchAgentType.COMMERCIAL_EVALUATION)
        recommendation = str(artifact.payload.get("recommendation", "unknown"))
        return {
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": "commercial_evaluation_complete",
            "progress": 95,
            "pending_gate": None,
            "terminal_reason": None,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_phase_completed",
                    node="commercial_complete",
                    task_id=artifact.task_id,
                    status="completed",
                    message=f"Commercial Evaluation v2 completed: {recommendation}.",
                ).model_dump(mode="json")
            ],
        }

    async def _prepare_red_team(self, state: ResearchState) -> dict[str, Any]:
        commercial_task = self._task(state, ResearchAgentType.COMMERCIAL_EVALUATION)
        task = ResearchTask(
            task_id=f"task_{state['project_id']}_red_team_policy_revision_v2",
            project_id=state["project_id"],
            agent_type=ResearchAgentType.RED_TEAM,
            goal=("攻击 AI 原生家庭安防策略、验证和商业结论，生成证据约束的定向返工要求。"),
            scope={
                "opportunity_ids": list(dict.fromkeys(state.get("selected_innovation_ids", []))),
                "challenges": [],
            },
            required_artifacts=[
                ResearchAgentType.USER_RESEARCH.value,
                ResearchAgentType.COMPETITOR_RESEARCH.value,
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
                ResearchAgentType.TECHNICAL_FEASIBILITY.value,
                ResearchAgentType.SECURITY_POLICY.value,
                ResearchAgentType.POLICY_VERIFICATION.value,
                ResearchAgentType.COMMERCIAL_EVALUATION.value,
            ],
            evidence_rules=commercial_task.evidence_rules,
            budget=ResearchBudget(
                max_pages=commercial_task.budget.max_pages,
                max_iterations=state.get("max_iterations", 2),
                deadline_seconds=180,
            ),
            depends_on=[commercial_task.task_id],
            acceptance_checks=[
                "all_attack_dimensions_covered",
                "all_factual_findings_evidence_bound",
                "verdict_computed_by_backend",
                "retry_targets_derived_from_current_artifacts",
                "rejected_scope_has_safe_fallback",
            ],
        )
        plan = [
            item
            for item in self._task_plan(state)
            if item.agent_type is not ResearchAgentType.RED_TEAM
        ]
        plan.append(task)
        return {
            "task_plan": [item.model_dump(mode="json") for item in plan],
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": "red_team_preparation",
            "progress": 96,
            "node_history": [self._event("prepare_red_team", task, "prepared")],
        }

    async def _red_team(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state,
            ResearchAgentType.RED_TEAM,
            "red_team_policy_revision",
            97,
            accepted_statuses={ResearchTaskStatus.COMPLETED, ResearchTaskStatus.PARTIAL},
        )

    async def _prepare_red_team_source_recovery(self, state: ResearchState) -> dict[str, Any]:
        artifact = _parse_red_team_artifact(
            self._artifact(state, ResearchAgentType.RED_TEAM)
        )
        gaps = artifact.payload.red_team_gaps
        if not gaps:
            raise WorkflowContractError(
                "needs_more_evidence red-team result requires explicit gaps"
            )
        request = WorkflowSourceRecoveryRequest(
            project_id=state["project_id"],
            source_artifact_id=artifact.artifact_id,
            source_task_id=artifact.task_id,
            gap_ids=[item.gap_id for item in gaps][:30],
            questions=[item.question for item in gaps][:30],
            affected_agent_types=[ResearchAgentType.RED_TEAM.value],
        )
        return {
            "pending_source_recovery": request.model_dump(mode="json"),
            "outcome": WorkflowOutcome.AWAITING_SOURCE_RECOVERY.value,
            "current_stage": "red_team_source_recovery",
            "progress": 97,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_source_recovery_pending",
                    node="prepare_red_team_source_recovery",
                    task_id=artifact.task_id,
                    status="waiting",
                    message="等待用户补充红队要求的证据、企业资料或授权说明。",
                ).model_dump(mode="json")
            ],
        }

    async def _red_team_source_recovery_gate(self, state: ResearchState) -> dict[str, Any]:
        pending = state.get("pending_source_recovery")
        if pending is None:
            raise WorkflowContractError("red-team source recovery has no pending request")
        request = WorkflowSourceRecoveryRequest.model_validate(pending)
        recovery = SourceRecovery.model_validate(interrupt(request.model_dump(mode="json")))
        update = prepare_source_recovery_resume(state, recovery)
        task = self._task(state, ResearchAgentType.RED_TEAM)
        if task.task_id not in update["affected_task_ids"]:
            raise WorkflowContractError("source recovery does not target red-team task")
        return {
            **update,
            "pending_source_recovery": None,
            "outcome": WorkflowOutcome.RUNNING.value,
        }

    async def _prepare_red_team_revision(self, state: ResearchState) -> dict[str, Any]:
        artifact = _parse_red_team_artifact(
            self._artifact(state, ResearchAgentType.RED_TEAM)
        )
        if not artifact.payload.revision_requests:
            raise WorkflowContractError("revise verdict requires a RevisionRequest")
        request = artifact.payload.revision_requests[0]
        return {
            "iteration": state.get("iteration", 0) + 1,
            "affected_task_ids": request.affected_task_ids,
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": "red_team_targeted_revision",
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_revision_started",
                    node="prepare_red_team_revision",
                    task_id=artifact.task_id,
                    status="running",
                    message=(
                        f"红队从 {request.resume_from_agent} 恢复；"
                        f"受影响任务：{','.join(request.affected_task_ids)}"
                    ),
                ).model_dump(mode="json")
            ],
        }

    async def _red_team_revision_dispatch(self, state: ResearchState) -> dict[str, Any]:
        return {
            "current_stage": "red_team_revision_dispatch",
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_revision_dispatched",
                    node="red_team_revision_dispatch",
                    status="completed",
                    message="已定位最早受影响 Agent；后续依赖节点将按主图重新运行。",
                ).model_dump(mode="json")
            ],
        }

    async def _red_team_research_revision(self, state: ResearchState) -> dict[str, Any]:
        return {
            "current_stage": "red_team_research_revision",
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_revision_dispatched",
                    node="red_team_research_revision",
                    status="running",
                    message="只重跑受影响的用户研究或竞品研究，再重新汇合。",
                ).model_dump(mode="json")
            ],
        }

    async def _red_team_complete(self, state: ResearchState) -> dict[str, Any]:
        artifact = _parse_red_team_artifact(
            self._artifact(state, ResearchAgentType.RED_TEAM)
        )
        return {
            "outcome": WorkflowOutcome.AWAITING_SCENARIO_VALIDATION.value,
            "current_stage": "red_team_passed",
            "progress": 98,
            "terminal_reason": "goal_to_guard_demo_not_implemented",
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_phase_completed",
                    node="red_team_complete",
                    task_id=artifact.task_id,
                    status="passed",
                    message="红队通过，等待 Goal-to-Guard 场景 Demo。",
                ).model_dump(mode="json")
            ],
        }

    async def _red_team_human_review(self, state: ResearchState) -> dict[str, Any]:
        artifact = _parse_red_team_artifact(
            self._artifact(state, ResearchAgentType.RED_TEAM)
        )
        return {
            "outcome": WorkflowOutcome.AWAITING_RED_TEAM_REVIEW.value,
            "current_stage": "red_team_human_review",
            "progress": 97,
            "terminal_reason": "privacy_consent_or_intervention_requires_human_review",
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_phase_completed",
                    node="red_team_human_review",
                    task_id=artifact.task_id,
                    status="waiting",
                    message="隐私、授权或高风险干预需要人工决定。",
                ).model_dump(mode="json")
            ],
        }

    async def _red_team_rejected(self, state: ResearchState) -> dict[str, Any]:
        artifact = _parse_red_team_artifact(
            self._artifact(state, ResearchAgentType.RED_TEAM)
        )
        return {
            "outcome": WorkflowOutcome.REJECTED.value,
            "current_stage": "red_team_rejected",
            "progress": 100,
            "terminal_reason": "irreducible_critical_red_team_finding",
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_finished",
                    node="red_team_rejected",
                    task_id=artifact.task_id,
                    status="rejected",
                    message="当前方案被淘汰；Artifact 已保留安全降级方案和重启条件。",
                ).model_dump(mode="json")
            ],
        }

    async def _awaiting_policy_revision(self, state: ResearchState) -> dict[str, Any]:
        artifact = self._artifact(state, ResearchAgentType.POLICY_VERIFICATION)
        return {
            "outcome": WorkflowOutcome.AWAITING_POLICY_REVISION.value,
            "current_stage": "policy_revision_pending",
            "progress": 88,
            "terminal_reason": "policy_verification_failed",
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_phase_completed",
                    node="awaiting_policy_revision",
                    task_id=artifact.task_id,
                    status=WorkflowOutcome.AWAITING_POLICY_REVISION,
                    message="Policy verification failed; wait for targeted revision.",
                ).model_dump(mode="json")
            ],
        }

    async def _prepare_research_revision(self, state: ResearchState) -> dict[str, Any]:
        return self._prepare_revision(state, "targeted_research", self._research_task_ids(state))

    async def _ecosystem_opportunity(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state,
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
            "ecosystem_opportunity",
            50,
            accepted_statuses={
                ResearchTaskStatus.COMPLETED,
                ResearchTaskStatus.PARTIAL,
                ResearchTaskStatus.BLOCKED,
                ResearchTaskStatus.NEEDS_REVISION,
            },
        )

    async def _evaluate_ai_native_gate(self, state: ResearchState) -> dict[str, Any]:
        artifact = self._artifact(state, ResearchAgentType.ECOSYSTEM_OPPORTUNITY)
        result = AINativeEcosystemGate().evaluate(artifact)
        return {
            "ai_native_gate": result.model_dump(mode="json"),
            "current_stage": "ai_native_gate_evaluation",
            "progress": 55,
            "node_history": [
                WorkflowEvent(
                    event_type="ai_native_ecosystem_gate_evaluated",
                    node="evaluate_ai_native_gate",
                    task_id=artifact.task_id,
                    status=("human_review_required" if result.ready_for_human_gate else "blocked"),
                    message=(
                        f"{len(result.eligible_opportunity_ids)} 个机会通过确定性检查，"
                        f"{len(result.blocked_opportunity_ids)} 个机会被阻止。"
                    ),
                ).model_dump(mode="json")
            ],
        }

    async def _prepare_ai_native_gate(self, state: ResearchState) -> dict[str, Any]:
        result = AINativeEcosystemGateResult.model_validate(state["ai_native_gate"])
        artifact = self._artifact(state, ResearchAgentType.ECOSYSTEM_OPPORTUNITY)
        return self._prepare_gate(
            state,
            GateName.AI_NATIVE_ECOSYSTEM,
            {
                "source_artifact_id": artifact.artifact_id,
                "eligible_opportunity_ids": result.eligible_opportunity_ids,
                "blocked_opportunity_ids": result.blocked_opportunity_ids,
                "assessments": [item.model_dump(mode="json") for item in result.assessments],
                "revision_requests": [
                    item.model_dump(mode="json") for item in result.revision_requests
                ],
                "source_recovery_gap_ids": result.source_recovery_gap_ids,
                "source_recovery_questions": result.source_recovery_questions,
            },
            "ai_native_ecosystem_approval",
            58,
        )

    async def _ai_native_gate(self, state: ResearchState) -> dict[str, Any]:
        return self._handle_gate(state, GateName.AI_NATIVE_ECOSYSTEM)

    async def _prepare_ecosystem_revision(self, state: ResearchState) -> dict[str, Any]:
        task = self._task(state, ResearchAgentType.ECOSYSTEM_OPPORTUNITY)
        revision_state = ResearchState(**state)
        revision_state["affected_task_ids"] = []
        return self._prepare_revision(
            revision_state, "ecosystem_opportunity_revision", [task.task_id]
        )

    async def _prepare_source_recovery(self, state: ResearchState) -> dict[str, Any]:
        result = AINativeEcosystemGateResult.model_validate(state["ai_native_gate"])
        if not result.source_recovery_gap_ids or not result.source_recovery_questions:
            raise WorkflowContractError(
                "AI-native research_more requires ecosystem opportunity source gaps"
            )
        request = WorkflowSourceRecoveryRequest(
            project_id=state["project_id"],
            source_artifact_id=result.source_artifact_id,
            source_task_id=result.source_task_id,
            gap_ids=result.source_recovery_gap_ids,
            questions=result.source_recovery_questions,
        )
        return {
            "pending_source_recovery": request.model_dump(mode="json"),
            "outcome": WorkflowOutcome.AWAITING_SOURCE_RECOVERY.value,
            "current_stage": "ecosystem_opportunity_source_recovery",
            "progress": 58,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_source_recovery_pending",
                    node="prepare_source_recovery",
                    task_id=result.source_task_id,
                    status="waiting",
                    message="等待用户通过统一 Source Recovery 补充生态机会证据。",
                ).model_dump(mode="json")
            ],
        }

    async def _source_recovery_gate(self, state: ResearchState) -> dict[str, Any]:
        pending = state.get("pending_source_recovery")
        if pending is None:
            raise WorkflowContractError("source recovery gate has no pending request")
        request = WorkflowSourceRecoveryRequest.model_validate(pending)
        raw_recovery = interrupt(request.model_dump(mode="json"))
        recovery = SourceRecovery.model_validate(raw_recovery)
        update = prepare_source_recovery_resume(state, recovery)
        affected_task = self._task(state, ResearchAgentType.ECOSYSTEM_OPPORTUNITY)
        if affected_task.task_id not in update["affected_task_ids"]:
            raise WorkflowContractError(
                "source recovery does not target ecosystem opportunity task"
            )
        return {
            **update,
            "pending_source_recovery": None,
            "outcome": WorkflowOutcome.RUNNING.value,
        }

    async def _prepare_technical_feasibility(self, state: ResearchState) -> dict[str, Any]:
        selected_ids = list(dict.fromkeys(state.get("selected_innovation_ids", [])))
        if not selected_ids:
            raise WorkflowContractError(
                "technical feasibility requires Human Gate selected opportunities"
            )
        opportunity_task = self._task(state, ResearchAgentType.ECOSYSTEM_OPPORTUNITY)
        task = ResearchTask(
            task_id=f"task_{state['project_id']}_technical_feasibility",
            project_id=state["project_id"],
            agent_type=ResearchAgentType.TECHNICAL_FEASIBILITY,
            goal=(
                "逐项验证已批准生态机会所需的设备能力、数据、接口、部署、性能、"
                "隐私、权限与失败降级条件，并限定可验证 Demo 的技术边界。"
            ),
            scope={"selected_opportunity_ids": selected_ids},
            required_artifacts=[
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
                "device_capability_graph",
            ],
            evidence_rules=opportunity_task.evidence_rules,
            budget=ResearchBudget(
                max_pages=opportunity_task.budget.max_pages,
                max_iterations=state.get("max_iterations", 2),
                deadline_seconds=180,
            ),
            depends_on=[opportunity_task.task_id],
            acceptance_checks=[
                "selected_opportunities_assessed",
                "technical_dimensions_complete",
                "device_capability_graph_reconciled",
                "deterministic_verdict",
            ],
        )
        plan = self._task_plan(state)
        plan = [item for item in plan if item.agent_type is not task.agent_type]
        plan.append(task)
        return {
            "task_plan": [item.model_dump(mode="json") for item in plan],
            "affected_task_ids": [],
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": "technical_feasibility_preparation",
            "progress": 60,
            "node_history": [self._event("prepare_technical_feasibility", task, "prepared")],
        }

    async def _technical_feasibility(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state,
            ResearchAgentType.TECHNICAL_FEASIBILITY,
            "technical_feasibility",
            68,
            accepted_statuses={
                ResearchTaskStatus.COMPLETED,
                ResearchTaskStatus.PARTIAL,
            },
        )

    async def _prepare_technical_source_recovery(self, state: ResearchState) -> dict[str, Any]:
        artifact = self._artifact(state, ResearchAgentType.TECHNICAL_FEASIBILITY)
        gaps = artifact.payload.get("portfolio_gaps", [])
        gap_ids = list(
            dict.fromkeys(
                str(item.get("gap_id"))
                for item in gaps
                if isinstance(item, dict) and item.get("gap_id")
            )
        )
        questions = list(
            dict.fromkeys(
                str(item.get("question"))
                for item in gaps
                if isinstance(item, dict) and item.get("question")
            )
        )
        if not gap_ids or not questions:
            raise WorkflowContractError(
                "insufficient technical feasibility requires explicit source gaps"
            )
        request = WorkflowSourceRecoveryRequest(
            project_id=state["project_id"],
            source_artifact_id=artifact.artifact_id,
            source_task_id=artifact.task_id,
            gap_ids=gap_ids[:30],
            questions=questions[:30],
            affected_agent_types=[ResearchAgentType.TECHNICAL_FEASIBILITY.value],
        )
        return {
            "pending_source_recovery": request.model_dump(mode="json"),
            "outcome": WorkflowOutcome.AWAITING_SOURCE_RECOVERY.value,
            "current_stage": "technical_feasibility_source_recovery",
            "progress": 68,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_source_recovery_pending",
                    node="prepare_technical_source_recovery",
                    task_id=artifact.task_id,
                    status="waiting",
                    message="等待用户补充设备 API、部署、性能或内部测试证据。",
                ).model_dump(mode="json")
            ],
        }

    async def _technical_source_recovery_gate(self, state: ResearchState) -> dict[str, Any]:
        pending = state.get("pending_source_recovery")
        if pending is None:
            raise WorkflowContractError("technical source recovery has no pending request")
        request = WorkflowSourceRecoveryRequest.model_validate(pending)
        recovery = SourceRecovery.model_validate(interrupt(request.model_dump(mode="json")))
        update = prepare_source_recovery_resume(state, recovery)
        task = self._task(state, ResearchAgentType.TECHNICAL_FEASIBILITY)
        if task.task_id not in update["affected_task_ids"]:
            raise WorkflowContractError(
                "source recovery does not target technical feasibility task"
            )
        return {
            **update,
            "pending_source_recovery": None,
            "outcome": WorkflowOutcome.RUNNING.value,
        }

    async def _prepare_security_policy(self, state: ResearchState) -> dict[str, Any]:
        selected_ids = list(dict.fromkeys(state.get("selected_innovation_ids", [])))
        if not selected_ids:
            raise WorkflowContractError("security policy requires selected opportunities")
        technical_task = self._task(state, ResearchAgentType.TECHNICAL_FEASIBILITY)
        task = ResearchTask(
            task_id=f"task_{state['project_id']}_security_policy",
            project_id=state["project_id"],
            agent_type=ResearchAgentType.SECURITY_POLICY,
            goal="Compile feasible ecosystem opportunities into a safe dry-run policy DSL.",
            scope={"selected_opportunity_ids": selected_ids},
            required_artifacts=[
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
                ResearchAgentType.TECHNICAL_FEASIBILITY.value,
            ],
            evidence_rules=technical_task.evidence_rules,
            budget=ResearchBudget(
                max_pages=technical_task.budget.max_pages,
                max_iterations=state.get("max_iterations", 2),
                deadline_seconds=180,
            ),
            depends_on=[technical_task.task_id],
            acceptance_checks=[
                "dry_run_only",
                "authorized_signals_only",
                "allowed_interventions_only",
                "five_deterministic_fallbacks",
            ],
        )
        plan = self._task_plan(state)
        plan = [item for item in plan if item.agent_type is not task.agent_type]
        plan.append(task)
        return {
            "task_plan": [item.model_dump(mode="json") for item in plan],
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": "security_policy_preparation",
            "progress": 72,
            "node_history": [self._event("prepare_security_policy", task, "prepared")],
        }

    async def _security_policy(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state,
            ResearchAgentType.SECURITY_POLICY,
            "security_policy",
            78,
            accepted_statuses={ResearchTaskStatus.COMPLETED, ResearchTaskStatus.PARTIAL},
        )

    async def _prepare_policy_verification(self, state: ResearchState) -> dict[str, Any]:
        policy_task = self._task(state, ResearchAgentType.SECURITY_POLICY)
        task = ResearchTask(
            task_id=f"task_{state['project_id']}_policy_verification",
            project_id=state["project_id"],
            agent_type=ResearchAgentType.POLICY_VERIFICATION,
            goal="Run deterministic dry-run scenarios against the compiled policy DSL.",
            scope={"policy_artifact_id": None, "scenarios": []},
            required_artifacts=[ResearchAgentType.SECURITY_POLICY.value],
            evidence_rules=policy_task.evidence_rules,
            budget=ResearchBudget(max_pages=0, max_iterations=1, deadline_seconds=60),
            depends_on=[policy_task.task_id],
            acceptance_checks=[
                "dry_run_only",
                "risk_rules_exercised",
                "five_fallbacks_exercised",
                "deterministic_assertions",
            ],
        )
        plan = self._task_plan(state)
        plan = [item for item in plan if item.agent_type is not task.agent_type]
        plan.append(task)
        return {
            "task_plan": [item.model_dump(mode="json") for item in plan],
            "outcome": WorkflowOutcome.RUNNING.value,
            "current_stage": "policy_verification_preparation",
            "progress": 80,
            "node_history": [self._event("prepare_policy_verification", task, "prepared")],
        }

    async def _policy_verification(self, state: ResearchState) -> dict[str, Any]:
        return await self._run_planned_agent(
            state,
            ResearchAgentType.POLICY_VERIFICATION,
            "policy_verification",
            86,
            accepted_statuses={ResearchTaskStatus.COMPLETED, ResearchTaskStatus.PARTIAL},
        )

    async def _policy_verification_complete(self, state: ResearchState) -> dict[str, Any]:
        artifact = self._artifact(state, ResearchAgentType.POLICY_VERIFICATION)
        verification_status = artifact.payload.get("verification_status")
        if verification_status == "failed":
            outcome = WorkflowOutcome.AWAITING_POLICY_REVISION
            reason = "policy_verification_failed"
        elif verification_status == "inconclusive":
            outcome = WorkflowOutcome.INCONCLUSIVE
            reason = "policy_verification_inconclusive"
        else:
            outcome = WorkflowOutcome.AWAITING_COMMERCIAL_EVALUATION
            reason = "commercial_evaluation_next"
        coverage = artifact.payload.get("coverage", {})
        return {
            "outcome": outcome.value,
            "current_stage": "policy_verification_complete",
            "progress": 88,
            "pending_gate": None,
            "terminal_reason": reason,
            "node_history": [
                WorkflowEvent(
                    event_type="workflow_phase_completed",
                    node="policy_verification_complete",
                    task_id=artifact.task_id,
                    status=outcome,
                    message=(
                        "Security Policy dry-run verification completed: "
                        f"{coverage.get('passed_count', 0)} passed, "
                        f"{coverage.get('failed_count', 0)} failed."
                    ),
                ).model_dump(mode="json")
            ],
        }

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
        accepted_statuses: set[ResearchTaskStatus] | None = None,
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
        accepted = accepted_statuses or {ResearchTaskStatus.COMPLETED}
        if allow_partial and accepted_statuses is None:
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
    def _route_ai_native_decision(state: ResearchState) -> str:
        decision = state["routing_decision"]
        if decision in {DecisionAction.REVISE, DecisionAction.RESEARCH_MORE} and state.get(
            "iteration", 0
        ) >= state.get("max_iterations", 2):
            return "inconclusive"
        return decision

    @staticmethod
    def _route_technical_feasibility(state: ResearchState) -> str:
        raw = state.get("artifacts", {}).get(ResearchAgentType.TECHNICAL_FEASIBILITY.value)
        if raw is None:
            raise WorkflowContractError("missing technical feasibility artifact")
        artifact = ResearchArtifact.model_validate(raw)
        coverage = artifact.payload.get("coverage", {})
        advancing = int(coverage.get("demo_feasible_count", 0)) + int(
            coverage.get("conditionally_feasible_count", 0)
        )
        if advancing:
            return "advance"
        if int(coverage.get("insufficient_evidence_count", 0)):
            if state.get("iteration", 0) < state.get("max_iterations", 2):
                return "research_more"
        return "inconclusive"

    @staticmethod
    def _route_policy_verification_complete(state: ResearchState) -> str:
        raw = state.get("artifacts", {}).get(ResearchAgentType.POLICY_VERIFICATION.value)
        if raw is None:
            raise WorkflowContractError("missing policy verification artifact")
        artifact = ResearchArtifact.model_validate(raw)
        status = str(artifact.payload.get("verification_status", ""))
        if status == "failed":
            return "revision"
        if status == "inconclusive":
            return "inconclusive"
        if status not in {"passed", "conditionally_passed"}:
            raise WorkflowContractError(f"unsupported policy verification status: {status}")
        return "advance"

    @staticmethod
    def _route_commercial_evaluation(state: ResearchState) -> str:
        raw = state.get("artifacts", {}).get(ResearchAgentType.COMMERCIAL_EVALUATION.value)
        if raw is None:
            raise WorkflowContractError("missing commercial evaluation artifact")
        artifact = ResearchArtifact.model_validate(raw)
        recommendation = str(artifact.payload.get("recommendation", ""))
        if recommendation == "needs_more_evidence":
            if state.get("iteration", 0) >= state.get("max_iterations", 2):
                return "inconclusive"
            return "research_more"
        if recommendation not in {
            "recommend_for_validation",
            "conditional",
            "do_not_recommend",
        }:
            raise WorkflowContractError(f"unsupported commercial recommendation: {recommendation}")
        return "advance"

    @staticmethod
    def _route_red_team(state: ResearchState) -> str:
        raw = state.get("artifacts", {}).get(ResearchAgentType.RED_TEAM.value)
        if raw is None:
            raise WorkflowContractError("missing red-team artifact")
        artifact = _parse_red_team_artifact(ResearchArtifact.model_validate(raw))
        verdict = artifact.payload.verdict
        if verdict.value in {
            "revise",
            "needs_more_evidence",
        } and state.get("iteration", 0) >= state.get("max_iterations", 2):
            return "inconclusive"
        return verdict.value

    @staticmethod
    def _route_red_team_revision(state: ResearchState) -> str:
        raw = state.get("artifacts", {}).get(ResearchAgentType.RED_TEAM.value)
        if raw is None:
            raise WorkflowContractError("missing red-team artifact")
        artifact = _parse_red_team_artifact(ResearchArtifact.model_validate(raw))
        if not artifact.payload.revision_requests:
            raise WorkflowContractError("red-team revision has no RevisionRequest")
        resume_from = artifact.payload.revision_requests[0].resume_from_agent
        if resume_from in {
            ResearchAgentType.USER_RESEARCH.value,
            ResearchAgentType.COMPETITOR_RESEARCH.value,
        }:
            return "research"
        if resume_from not in {
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
            ResearchAgentType.TECHNICAL_FEASIBILITY.value,
            ResearchAgentType.SECURITY_POLICY.value,
            ResearchAgentType.POLICY_VERIFICATION.value,
            ResearchAgentType.COMMERCIAL_EVALUATION.value,
        }:
            raise WorkflowContractError(f"unsupported red-team resume agent: {resume_from}")
        return resume_from

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


def _parse_red_team_artifact(artifact: ResearchArtifact) -> RedTeamArtifact:
    # Local import keeps workflow contracts independent from Agent adapter imports.
    from app.agents.red_team_policy_revision.contracts import RedTeamArtifact

    return RedTeamArtifact.from_research_artifact(artifact)
