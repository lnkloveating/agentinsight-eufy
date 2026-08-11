"""Deterministic Evidence and Device Capability Graph gates."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.agents.ecosystem_opportunity.context import DeviceCapabilityGraphContext
from app.agents.ecosystem_opportunity.contracts import (
    EcosystemGateStatus,
    EcosystemOpportunityArtifact,
    EcosystemOpportunityCandidate,
    EcosystemOpportunityCoverage,
    EcosystemOpportunityGap,
    EcosystemOpportunityModelOutput,
    EcosystemOpportunityPayload,
    SolutionScope,
    ecosystem_opportunity_gap_id,
)
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchHandoff,
    ResearchHandoffStatus,
    ResearchTask,
    ResearchTaskStatus,
)


@dataclass(frozen=True)
class EcosystemOpportunityValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class EcosystemOpportunityOutputValidator:
    TARGET_CANDIDATES = 3
    MAXIMUM_CANDIDATES = 5

    def build_blocked(
        self,
        task: ResearchTask,
        context: AgentContext,
        graph: DeviceCapabilityGraphContext,
        issues: list[str],
    ) -> ResearchArtifact:
        question = "还需要补齐哪些用户研究和竞品生态证据，才能生成可验证的生态机会？"
        gap = EcosystemOpportunityGap(
            gap_id=ecosystem_opportunity_gap_id(question, []),
            question=question,
            reason="用户研究或竞品生态研究尚未通过主路径交接门禁。",
            required_evidence_types=[
                "user_research_artifact",
                "competitor_ecosystem_artifact",
            ],
            affected_opportunity_ids=[],
        )
        handoff = context.research_handoff
        payload = EcosystemOpportunityPayload(
            summary="上游研究尚未就绪；系统没有调用模型，也没有使用固定模板补造生态方案。",
            summary_evidence_ids=[],
            opportunities=[],
            portfolio_gaps=[gap],
            coverage=EcosystemOpportunityCoverage(
                generated_candidate_count=0,
                advancing_candidate_count=0,
                ecosystem_service_count=0,
                cited_user_evidence_count=0,
                cited_competitor_evidence_count=0,
                evidence_context_hash=self._context_hash(context, graph),
                handoff_status=(
                    handoff.status if handoff is not None else ResearchHandoffStatus.BLOCKED
                ),
            ),
        )
        return EcosystemOpportunityArtifact(
            artifact_id="artifact_pending",
            task_id=task.task_id,
            artifact_type=ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
            schema_version="1.0",
            status=ResearchTaskStatus.BLOCKED,
            payload=payload,
            evidence_ids=[],
            contradictions=[],
            unknowns=[question],
            quality_score=0,
            errors=list(dict.fromkeys(["ECOSYSTEM_OPPORTUNITY_HANDOFF_BLOCKED", *issues])),
        ).to_research_artifact()

    def validate(
        self,
        task: ResearchTask,
        context: AgentContext,
        graph: DeviceCapabilityGraphContext,
        output: EcosystemOpportunityModelOutput,
    ) -> ResearchArtifact:
        handoff = self._require_ready_handoff(context)
        user = context.upstream_artifacts.get(ResearchAgentType.USER_RESEARCH.value)
        competitor = context.upstream_artifacts.get(ResearchAgentType.COMPETITOR_RESEARCH.value)
        if user is None or competitor is None:
            raise EcosystemOpportunityValidationError(
                "Ecosystem Opportunity output lacks its two upstream Artifacts.",
                {"available_artifacts": sorted(context.upstream_artifacts)},
            )
        user_ids = set(user.evidence_ids)
        competitor_ids = set(competitor.evidence_ids)
        graph_ids = set(graph.evidence_ids)
        allowed = {
            *handoff.merged_evidence_ids,
            *handoff.supplemental_evidence_ids,
            *graph_ids,
        }
        cited = output.cited_evidence_ids()
        unsupported = sorted(cited - allowed)
        if unsupported:
            raise EcosystemOpportunityValidationError(
                "Ecosystem Opportunity output cited Evidence outside its input boundary.",
                {"unsupported_evidence_ids": unsupported},
            )
        if output.opportunities and not output.summary_evidence_ids:
            raise EcosystemOpportunityValidationError(
                "A factual ecosystem opportunity summary requires Evidence IDs.",
                {"field": "summary_evidence_ids"},
            )
        self._validate_diversity(output)
        allowed_gap_ids = set(
            handoff.competitor_projection.opportunity_signal_ids
            if handoff.competitor_projection is not None
            else []
        )

        candidates: list[EcosystemOpportunityCandidate] = []
        generated_gaps = [
            EcosystemOpportunityGap(
                gap_id=ecosystem_opportunity_gap_id(
                    gap.question, gap.affected_opportunity_ids
                ),
                **gap.model_dump(mode="python"),
            )
            for gap in output.portfolio_gaps
        ]
        for candidate in output.opportunities:
            candidate_ids = set(candidate.evidence_ids)
            gate_issues: list[str] = []
            if not candidate_ids & user_ids:
                gate_issues.append("missing_user_research_evidence")
            if not candidate_ids & competitor_ids:
                gate_issues.append("missing_competitor_ecosystem_evidence")
            unknown_gap_ids = sorted(set(candidate.competitor_gap_ids) - allowed_gap_ids)
            if unknown_gap_ids:
                raise EcosystemOpportunityValidationError(
                    "Candidate referenced an unknown competitor opportunity signal.",
                    {
                        "opportunity_id": candidate.opportunity_id,
                        "unknown_competitor_gap_ids": unknown_gap_ids,
                    },
                )
            if candidate.scope_level is SolutionScope.ECOSYSTEM_SERVICE:
                if len(candidate.ecosystem_blueprint.required_device_roles) < 2:
                    gate_issues.append("ecosystem_service_requires_multiple_device_roles")
                if not candidate.ecosystem_blueprint.cross_device_information_flows:
                    gate_issues.append("ecosystem_service_requires_cross_device_flow")

            role_graph_ids = {
                evidence_id
                for role in candidate.ecosystem_blueprint.required_device_roles
                for evidence_id in role.evidence_ids
            }
            graph_out_of_scope = sorted(role_graph_ids - graph_ids)
            if graph_out_of_scope:
                raise EcosystemOpportunityValidationError(
                    "Device role cited Evidence outside the Device Capability Graph.",
                    {
                        "opportunity_id": candidate.opportunity_id,
                        "unsupported_device_evidence_ids": graph_out_of_scope,
                    },
                )
            required_capabilities = list(
                dict.fromkeys(
                    [
                        *candidate.ecosystem_blueprint.required_capabilities,
                        *(
                            capability
                            for role in candidate.ecosystem_blueprint.required_device_roles
                            for capability in role.required_capabilities
                        ),
                    ]
                )
            )
            for capability in required_capabilities:
                facts = self._matching_facts(capability, graph)
                supported = [
                    fact
                    for fact in facts
                    if fact.assertion == "supported" and fact.availability == "available"
                ]
                contradicted = [
                    fact
                    for fact in facts
                    if fact.assertion == "unsupported" or fact.availability == "unavailable"
                ]
                if supported and not contradicted:
                    supporting_ids = {
                        evidence_id for fact in supported for evidence_id in fact.evidence_ids
                    }
                    if not role_graph_ids & supporting_ids:
                        gate_issues.append(f"missing_capability_evidence:{capability}")
                    continue
                hypothesis_is_explicit = any(
                    self._normalize(capability) in self._normalize(item)
                    for item in candidate.technical_hypotheses
                )
                if not hypothesis_is_explicit:
                    gate_issues.append(f"unverified_capability_not_hypothesis:{capability}")
                generated_gaps.append(self._capability_gap(candidate.opportunity_id, capability))
                if supported and contradicted:
                    gate_issues.append(f"capability_evidence_conflict:{capability}")
                elif contradicted:
                    gate_issues.append(f"capability_currently_unavailable:{capability}")

            candidates.append(
                EcosystemOpportunityCandidate(
                    **candidate.model_dump(mode="python"),
                    gate_status=(
                        EcosystemGateStatus.PASSED
                        if not gate_issues
                        else EcosystemGateStatus.BLOCKED
                    ),
                    gate_issues=list(dict.fromkeys(gate_issues)),
                )
            )

        advancing = [
            item for item in candidates if item.gate_status is EcosystemGateStatus.PASSED
        ]
        if len(advancing) < self.TARGET_CANDIDATES:
            question = (
                f"还需要哪些证据才能把可晋级生态机会从 {len(advancing)} 个补足到 "
                f"{self.TARGET_CANDIDATES} 个？"
            )
            generated_gaps.append(
                EcosystemOpportunityGap(
                    gap_id=ecosystem_opportunity_gap_id(
                        question, [item.opportunity_id for item in candidates]
                    ),
                    question=question,
                    reason="系统不会为了凑数复制固定门铃、包裹或老人照护模板。",
                    required_evidence_types=[
                        "user_safety_event_evidence",
                        "competitor_ecosystem_gap_evidence",
                        "device_capability_evidence",
                    ],
                    affected_opportunity_ids=[item.opportunity_id for item in candidates],
                )
            )
        gaps = self._unique_gaps(generated_gaps)
        status = (
            ResearchTaskStatus.COMPLETED
            if len(advancing) >= self.TARGET_CANDIDATES
            and handoff.status is ResearchHandoffStatus.READY
            else ResearchTaskStatus.PARTIAL
            if advancing
            else ResearchTaskStatus.BLOCKED
        )
        payload = EcosystemOpportunityPayload(
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            opportunities=candidates,
            portfolio_gaps=gaps,
            coverage=EcosystemOpportunityCoverage(
                generated_candidate_count=len(candidates),
                advancing_candidate_count=len(advancing),
                ecosystem_service_count=sum(
                    item.scope_level is SolutionScope.ECOSYSTEM_SERVICE
                    for item in candidates
                ),
                cited_user_evidence_count=len(cited & user_ids),
                cited_competitor_evidence_count=len(cited & competitor_ids),
                evidence_context_hash=self._context_hash(context, graph),
                handoff_status=handoff.status,
            ),
        )
        unknowns = list(
            dict.fromkeys(
                [
                    *output.unknowns,
                    *(gap.question for gap in gaps),
                    *graph.issues,
                    *user.unknowns,
                    *competitor.unknowns,
                ]
            )
        )
        return EcosystemOpportunityArtifact(
            artifact_id="artifact_pending",
            task_id=task.task_id,
            artifact_type=ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
            schema_version="1.0",
            status=status,
            payload=payload,
            evidence_ids=sorted(cited),
            contradictions=list(
                dict.fromkeys([*user.contradictions, *competitor.contradictions])
            ),
            unknowns=unknowns,
            quality_score=self._quality_score(
                generated=len(candidates),
                advancing=len(advancing),
                cites_graph=bool(cited & graph_ids),
                handoff_status=handoff.status,
            ),
            errors=[] if advancing else ["NO_ADVANCING_ECOSYSTEM_OPPORTUNITY"],
        ).to_research_artifact()

    @staticmethod
    def _require_ready_handoff(context: AgentContext) -> ResearchHandoff:
        handoff = context.research_handoff
        if handoff is None or not handoff.ready_for_ecosystem_opportunity:
            raise EcosystemOpportunityValidationError(
                "Ecosystem Opportunity Agent requires a ready ResearchHandoff.",
                {"handoff_status": handoff.status if handoff is not None else None},
            )
        return handoff

    @classmethod
    def _matching_facts(
        cls, capability: str, graph: DeviceCapabilityGraphContext
    ) -> list[Any]:
        normalized = cls._normalize(capability)
        return [
            fact
            for fact in graph.facts
            if normalized in {
                cls._normalize(fact.capability_key),
                cls._normalize(fact.capability_name),
            }
        ]

    @staticmethod
    def _capability_gap(opportunity_id: str, capability: str) -> EcosystemOpportunityGap:
        question = f"哪些设备和证据能够验证生态机会所需的“{capability}”能力？"
        return EcosystemOpportunityGap(
            gap_id=ecosystem_opportunity_gap_id(question, [opportunity_id]),
            question=question,
            reason="当前 Device Capability Graph 没有确认该能力可用，暂时只能作为技术假设。",
            required_evidence_types=["device_capability", "compatibility", "limitation"],
            affected_opportunity_ids=[opportunity_id],
        )

    @classmethod
    def _validate_diversity(cls, output: EcosystemOpportunityModelOutput) -> None:
        names: set[str] = set()
        goals: set[str] = set()
        for item in output.opportunities:
            name = cls._normalize(item.name)
            goal = cls._normalize(item.safety_goal)
            if name in names or goal in goals:
                raise EcosystemOpportunityValidationError(
                    "Ecosystem Opportunity output contains duplicate candidates.",
                    {"opportunity_id": item.opportunity_id},
                )
            names.add(name)
            goals.add(goal)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\w]+", "", value.casefold())

    @staticmethod
    def _unique_gaps(
        gaps: list[EcosystemOpportunityGap],
    ) -> list[EcosystemOpportunityGap]:
        by_question: dict[str, EcosystemOpportunityGap] = {}
        for gap in gaps:
            by_question.setdefault(gap.question.casefold().strip(), gap)
        return list(by_question.values())

    @staticmethod
    def _context_hash(
        context: AgentContext, graph: DeviceCapabilityGraphContext
    ) -> str:
        canonical = json.dumps(
            {
                "evidence_context_hash": (
                    context.evidence_context.context_hash
                    if context.evidence_context is not None
                    else None
                ),
                "capability_graph_hash": graph.context_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _quality_score(
        cls,
        *,
        generated: int,
        advancing: int,
        cites_graph: bool,
        handoff_status: ResearchHandoffStatus,
    ) -> float:
        score = 15.0
        score += min(generated / cls.TARGET_CANDIDATES, 1.0) * 20
        score += min(advancing / cls.TARGET_CANDIDATES, 1.0) * 45
        score += 15 if cites_graph else 0
        score += 5 if handoff_status is ResearchHandoffStatus.READY else 0
        return round(min(score, 100.0), 2)
