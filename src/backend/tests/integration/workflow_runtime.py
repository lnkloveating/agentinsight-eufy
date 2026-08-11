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
        invalid_competitor_attempts: int = 0,
    ) -> None:
        self.evidence_ready_on_attempt = evidence_ready_on_attempt
        self.fail_once = set(fail_once or set())
        self.competitor_ready_with_gaps = competitor_ready_with_gaps
        self.invalid_competitor_attempts = invalid_competitor_attempts
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
                    if (
                        self.call_counts[task.agent_type]
                        <= self.invalid_competitor_attempts
                    ):
                        payload = {
                            "schema_name": "competitor_a2a_foundation",
                            "specialist_outputs": [],
                        }
                    else:
                        if self.competitor_ready_with_gaps:
                            status = ResearchTaskStatus.PARTIAL
                            unknowns = [
                                "Recurring user-review evidence remains incomplete."
                            ]
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
        elif task.agent_type is ResearchAgentType.ECOSYSTEM_OPPORTUNITY:
            evidence_ids = _upstream_evidence(context)
            payload = _ecosystem_opportunity_payload(evidence_ids)

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
    opportunity = _task(
        project_id,
        "ecosystem_opportunity",
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        [user.task_id, competitor.task_id],
    )
    return [user, competitor, opportunity]


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


def _ecosystem_opportunity_payload(evidence_ids: list[str]) -> dict[str, object]:
    user_id = next(item for item in evidence_ids if "user_research" in item)
    competitor_id = next(item for item in evidence_ids if "competitor_research" in item)
    opportunity_id = "eco_continuous_guard"
    return {
        "schema_name": "ecosystem_opportunity_portfolio",
        "schema_version": "1.0",
        "summary": "Cross-device state understanding is ready for AI-native review.",
        "summary_evidence_ids": [user_id, competitor_id],
        "opportunities": [
            {
                "opportunity_id": opportunity_id,
                "name": "Continuous household safety guard",
                "scope_level": "ecosystem_service",
                "target_user": {
                    "persona_ids": ["persona_household"],
                    "description": "Households authorizing safety event metadata",
                },
                "problem": {
                    "pain_ids": ["pain_manual_context"],
                    "description": "People must manually combine device events.",
                },
                "safety_goal": "Continuously understand changing household safety risk.",
                "ecosystem_blueprint": {
                    "required_device_roles": [
                        {
                            "role_id": "role_perception",
                            "role_type": "primary_perception",
                            "description": "Capture authorized event metadata.",
                            "required_capabilities": [],
                            "optional": False,
                            "evidence_ids": [],
                        },
                        {
                            "role_id": "role_reasoning",
                            "role_type": "local_reasoning_hub",
                            "description": "Maintain household safety state.",
                            "required_capabilities": [],
                            "optional": False,
                            "evidence_ids": [],
                        },
                    ],
                    "required_capabilities": [],
                    "cross_device_information_flows": [
                        {
                            "flow_id": "flow_event_context",
                            "from_role_id": "role_perception",
                            "to_role_id": "role_reasoning",
                            "data_type": "authorized_event_metadata",
                            "purpose": "Update continuous safety state.",
                            "privacy_constraints": ["Use minimum metadata only."],
                            "fallback": "Fall back to a low-risk notification.",
                        }
                    ],
                    "deployment_target": "hybrid",
                    "privacy_boundary": "Raw media remains local by default.",
                    "permission_boundary": "High-impact actions require approval.",
                    "offline_behavior": "Run local low-risk safeguards.",
                    "fallback_behavior": "Ask the user when evidence is insufficient.",
                    "known_blind_spots": ["Offline devices reduce context."],
                },
                "ai_native_case": {
                    "open_ended_goal": "Protect the household as conditions change.",
                    "why_fixed_rules_are_insufficient": "Risk depends on time and context.",
                    "model_responsibilities": ["Interpret uncertain event sequences."],
                    "deterministic_responsibilities": ["Enforce permission boundaries."],
                    "ai_removal_test": {
                        "core_value_survives_without_ai": False,
                        "rationale": "Without AI only fixed notifications remain.",
                        "lost_capabilities_without_ai": ["Open goal interpretation."],
                        "evidence_ids": [user_id],
                    },
                    "learning_or_revision_loop": ["Revise policy after failed tests."],
                    "safety_constraints": ["Do not infer medical diagnoses."],
                },
                "competitor_gap_ids": ["signal_package_context"],
                "technical_hypotheses": [],
                "commercial_hypotheses": ["Pilot willingness requires validation."],
                "validation_plan": {
                    "validation_goal": "Find unsafe behavior before deployment.",
                    "required_scenario_types": ["normal", "failure", "adversarial"],
                    "success_conditions": ["Normal behavior avoids escalation."],
                    "failure_conditions": ["High risk is missed."],
                    "required_data": ["Authorized or simulated events."],
                    "human_review_points": ["Before policy activation."],
                },
                "evidence_ids": [user_id, competitor_id],
                "gate_status": "passed",
                "gate_issues": [],
            }
        ],
        "portfolio_gaps": [
            {
                "gap_id": "gap_more_opportunities",
                "question": "Which additional safety goals have enough evidence?",
                "reason": "The current evidence supports one opportunity.",
                "required_evidence_types": ["user_opinion"],
                "affected_opportunity_ids": [opportunity_id],
            }
        ],
        "coverage": {
            "target_candidate_count": 3,
            "maximum_candidate_count": 5,
            "generated_candidate_count": 1,
            "advancing_candidate_count": 1,
            "ecosystem_service_count": 1,
            "cited_user_evidence_count": 1,
            "cited_competitor_evidence_count": 1,
            "evidence_context_hash": "a" * 64,
            "handoff_status": "ready",
        },
    }
