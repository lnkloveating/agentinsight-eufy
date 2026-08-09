"""仅供工作流测试使用的确定性 Runtime；生产代码不会导入本模块。"""

from collections import Counter

from app.workflows.contracts import (
    AgentContext,
    RedTeamDirective,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)


class TestAgentRuntime:
    __test__ = False

    def __init__(
        self,
        *,
        evidence_ready_on_attempt: int = 1,
        fail_once: set[ResearchAgentType] | None = None,
        competitor_ready_with_gaps: bool = False,
    ) -> None:
        self.evidence_ready_on_attempt = evidence_ready_on_attempt
        self.fail_once = set(fail_once or set())
        self.competitor_ready_with_gaps = competitor_ready_with_gaps
        self.calls: list[ResearchAgentType] = []
        self.call_counts: Counter[ResearchAgentType] = Counter()
        self.contexts: dict[ResearchAgentType, AgentContext] = {}

    async def execute(
        self,
        task: ResearchTask,
        context: AgentContext,
    ) -> ResearchArtifact:
        self.calls.append(task.agent_type)
        self.call_counts[task.agent_type] += 1
        self.contexts[task.agent_type] = context
        if task.agent_type in self.fail_once:
            self.fail_once.remove(task.agent_type)
            raise RuntimeError(f"planned failure:{task.agent_type}")

        payload: dict[str, object] = {}
        evidence_ids: list[str] = []
        unknowns: list[str] = []
        status = ResearchTaskStatus.COMPLETED
        if task.agent_type is ResearchAgentType.RESEARCH_MANAGER:
            payload = {"tasks": [item.model_dump(mode="json") for item in _task_plan(task)]}
        elif task.agent_type in {
            ResearchAgentType.USER_RESEARCH,
            ResearchAgentType.COMPETITOR_RESEARCH,
        }:
            if self.call_counts[task.agent_type] < self.evidence_ready_on_attempt:
                status = ResearchTaskStatus.PARTIAL
            else:
                evidence_id = f"ev_test_{task.agent_type}"
                evidence_ids = [evidence_id]
                if task.agent_type is ResearchAgentType.USER_RESEARCH:
                    payload = _user_research_payload(evidence_id)
                else:
                    if self.competitor_ready_with_gaps:
                        status = ResearchTaskStatus.PARTIAL
                        unknowns = ["Recurring user-review evidence remains incomplete."]
                    payload = _competitor_synthesis_payload(
                        evidence_id,
                        with_gaps=self.competitor_ready_with_gaps,
                    )
        elif task.agent_type is ResearchAgentType.PRODUCT_TECHNICAL:
            evidence_ids = _upstream_evidence(context)
            payload = {"innovation_ids": ["inv_one", "inv_two", "inv_three"]}
        elif task.agent_type is ResearchAgentType.COMMERCIAL_EVALUATION:
            evidence_ids = _upstream_evidence(context)
            payload = {"assessed_innovation_ids": ["inv_one", "inv_two", "inv_three"]}
        elif task.agent_type is ResearchAgentType.RED_TEAM:
            evidence_ids = _upstream_evidence(context)
            payload = {
                "directive": RedTeamDirective(
                    decision="pass",
                    severity="medium",
                    required_actions=[],
                ).model_dump(mode="json")
            }
        elif task.agent_type is ResearchAgentType.CANDIDATE_SYNTHESIS:
            evidence_ids = _upstream_evidence(context)
            payload = {
                "innovation_ids": ["inv_one", "inv_two", "inv_three"],
                "recommendation": "investigate",
            }
        elif task.agent_type is ResearchAgentType.VALIDATION:
            evidence_ids = _upstream_evidence(context)
            payload = {"status": "test_validation_completed"}
        elif task.agent_type is ResearchAgentType.FINAL_SYNTHESIS:
            evidence_ids = _upstream_evidence(context)
            payload = {"recommendation": "investigate"}

        return ResearchArtifact(
            artifact_id=f"artifact_{task.task_id}_{self.call_counts[task.agent_type]}",
            task_id=task.task_id,
            artifact_type=task.agent_type,
            status=status,
            payload=payload,
            evidence_ids=evidence_ids,
            unknowns=unknowns,
            quality_score=90 if status is ResearchTaskStatus.COMPLETED else 70,
        )


def _task_plan(manager_task: ResearchTask) -> list[ResearchTask]:
    project_id = manager_task.project_id
    user = _task(project_id, "user", ResearchAgentType.USER_RESEARCH)
    competitor = _task(project_id, "competitor", ResearchAgentType.COMPETITOR_RESEARCH)
    product = _task(
        project_id,
        "product",
        ResearchAgentType.PRODUCT_TECHNICAL,
        [user.task_id, competitor.task_id],
    )
    commercial = _task(
        project_id,
        "commercial",
        ResearchAgentType.COMMERCIAL_EVALUATION,
        [product.task_id],
    )
    red_team = _task(
        project_id,
        "redteam",
        ResearchAgentType.RED_TEAM,
        [commercial.task_id],
    )
    candidate = _task(
        project_id,
        "candidate",
        ResearchAgentType.CANDIDATE_SYNTHESIS,
        [red_team.task_id],
    )
    validation = _task(
        project_id,
        "validation",
        ResearchAgentType.VALIDATION,
        [candidate.task_id],
    )
    final = _task(
        project_id,
        "final",
        ResearchAgentType.FINAL_SYNTHESIS,
        [validation.task_id],
    )
    return [user, competitor, product, commercial, red_team, candidate, validation, final]


def _task(
    project_id: str,
    suffix: str,
    agent_type: ResearchAgentType,
    depends_on: list[str] | None = None,
) -> ResearchTask:
    return ResearchTask(
        task_id=f"task_{project_id}_{suffix}",
        project_id=project_id,
        agent_type=agent_type,
        goal=f"test goal:{agent_type}",
        required_artifacts=[agent_type],
        depends_on=depends_on or [],
        acceptance_checks=["schema_valid"],
    )


def _upstream_evidence(context: AgentContext) -> list[str]:
    return sorted(
        {
            evidence_id
            for artifact in context.upstream_artifacts.values()
            for evidence_id in artifact.evidence_ids
        }
    )


def _user_research_payload(evidence_id: str) -> dict[str, object]:
    return {
        "summary": "Users still combine event context manually.",
        "summary_evidence_ids": [evidence_id],
        "event_chains": [],
        "pain_points": [],
        "unmet_needs": [],
        "sample_biases": [],
        "research_gaps": [],
        "evidence_coverage": {
            "available_evidence_count": 1,
            "included_evidence_count": 1,
            "cited_evidence_count": 1,
            "independent_domain_count": 1,
            "user_opinion_evidence_count": 1,
            "context_hash": "a" * 64,
        },
    }


def _competitor_synthesis_payload(
    evidence_id: str,
    *,
    with_gaps: bool,
) -> dict[str, object]:
    gaps = (
        [
            {
                "scope_label": "Test Doorbell",
                "dimension": "user_review",
                "question": "Which repeated user opinions remain missing?",
                "reason": "The current review coverage is incomplete.",
                "severity": "medium",
            }
        ]
        if with_gaps
        else []
    )
    return {
        "schema_name": "competitor_synthesis_intelligence",
        "schema_version": "1.0",
        "supervisor_mode": "a2a_specialists_then_evidence_bounded_synthesis",
        "specialist_outputs": [
            {"specialist_type": "official_product"},
            {"specialist_type": "price_channel"},
            {"specialist_type": "user_review"},
        ],
        "summary": "Competitor evidence identifies a package-context opportunity.",
        "summary_evidence_ids": [evidence_id],
        "product_profiles": [
            {
                "scope_label": "Test Doorbell",
                "strengths": [
                    {
                        "point_id": "point_detection",
                        "dimension": "official_product",
                        "statement": "Package detection is documented.",
                        "explanation": "The controlled specialist output supports it.",
                        "confidence": 0.9,
                        "evidence_ids": [evidence_id],
                    }
                ],
                "weaknesses": [],
                "tradeoffs": [],
            }
        ],
        "comparative_insights": [],
        "opportunity_signals": [
            {
                "signal_id": "signal_package_context",
                "scope_labels": ["Test Doorbell"],
                "statement": "Package context warrants product validation.",
                "rationale": "Detection alone does not explain risk.",
                "validation_questions": ["Which context signals change risk?"],
                "hypothesis_status": "requires_product_agent_validation",
                "evidence_ids": [evidence_id],
            }
        ],
        "research_gaps": gaps,
        "coverage_matrix": [
            {
                "scope_label": "Test Doorbell",
                "official_product_evidence_ids": [evidence_id],
                "price_channel_evidence_ids": [evidence_id],
                "user_review_evidence_ids": [] if with_gaps else [evidence_id],
                "complete": not with_gaps,
            }
        ],
        "evidence_audit": {
            "status": "passed_with_gaps" if with_gaps else "passed",
            "allowed_evidence_count": 1,
            "cited_evidence_count": 1,
            "specialist_output_count": 3,
            "requested_product_count": 1,
            "represented_product_count": 1,
            "complete_product_count": 0 if with_gaps else 1,
            "independent_source_count": 1,
            "evidence_context_hash": "b" * 64,
        },
        "synthesis_status": "partial" if with_gaps else "completed",
    }
