"""Deterministic evidence, diversity and Event Understanding gates."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.agents.product_technical.contracts import (
    CandidateGateStatus,
    ProductOpportunityCandidate,
    ProductTechnicalArtifact,
    ProductTechnicalCoverage,
    ProductTechnicalGap,
    ProductTechnicalModelOutput,
    ProductTechnicalPayload,
)
from app.domain.innovation import EventUnderstandingGate
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
class ProductTechnicalValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class ProductTechnicalOutputValidator:
    TARGET_CANDIDATES = 3
    MAXIMUM_CANDIDATES = 5

    def __init__(self, event_gate: EventUnderstandingGate | None = None) -> None:
        self.event_gate = event_gate or EventUnderstandingGate()

    def build_blocked(
        self,
        task: ResearchTask,
        context: AgentContext,
        issues: list[str],
    ) -> ResearchArtifact:
        handoff = context.research_handoff
        question = "需要补齐哪些用户研究与竞品证据，才能生成可验证的未来产品候选？"
        gap = ProductTechnicalGap(
            question=question,
            reason="产品技术阶段没有收到通过主路径交接门的用户研究和竞品综合结果。",
            required_evidence_types=["user_research_artifact", "competitor_synthesis_artifact"],
            affected_candidate_ids=[],
        )
        payload = ProductTechnicalPayload(
            summary="上游研究交接未就绪，产品技术 Agent 未调用模型，也没有补造候选方案。",
            summary_evidence_ids=[],
            candidates=[],
            portfolio_gaps=[gap],
            coverage=ProductTechnicalCoverage(
                generated_candidate_count=0,
                advancing_candidate_count=0,
                cited_user_evidence_count=0,
                cited_competitor_evidence_count=0,
                evidence_context_hash=self._context_hash(context),
                handoff_status=(
                    handoff.status if handoff is not None else ResearchHandoffStatus.BLOCKED
                ),
            ),
        )
        return ProductTechnicalArtifact(
            artifact_id="artifact_pending",
            task_id=task.task_id,
            artifact_type=ResearchAgentType.PRODUCT_TECHNICAL.value,
            schema_version="1.0",
            status=ResearchTaskStatus.BLOCKED,
            payload=payload,
            evidence_ids=[],
            contradictions=[],
            unknowns=[question],
            quality_score=0,
            errors=list(dict.fromkeys(["PRODUCT_TECHNICAL_HANDOFF_BLOCKED", *issues])),
        ).to_research_artifact()

    def validate(
        self,
        task: ResearchTask,
        context: AgentContext,
        output: ProductTechnicalModelOutput,
    ) -> ResearchArtifact:
        handoff = self._require_ready_handoff(context)
        user = context.upstream_artifacts.get(ResearchAgentType.USER_RESEARCH.value)
        competitor = context.upstream_artifacts.get(ResearchAgentType.COMPETITOR_RESEARCH.value)
        if user is None or competitor is None:
            raise ProductTechnicalValidationError(
                "Product Technical output lacks its two upstream Artifacts.",
                {"available_artifacts": sorted(context.upstream_artifacts)},
            )
        user_ids = set(user.evidence_ids)
        competitor_ids = set(competitor.evidence_ids)
        allowed = set(handoff.merged_evidence_ids)
        cited = output.cited_evidence_ids()
        unsupported = sorted(cited - allowed)
        if unsupported:
            raise ProductTechnicalValidationError(
                "Product Technical output cited Evidence outside the research handoff.",
                {"unsupported_evidence_ids": unsupported},
            )
        self._validate_candidate_diversity(output)
        allowed_gap_ids = set(
            handoff.competitor_projection.opportunity_signal_ids
            if handoff.competitor_projection is not None
            else []
        )

        candidates: list[ProductOpportunityCandidate] = []
        for candidate in output.candidates:
            candidate_ids = set(candidate.evidence_ids)
            boundary_issues: list[str] = []
            if not candidate_ids & user_ids:
                boundary_issues.append("missing_user_research_evidence")
            if not candidate_ids & competitor_ids:
                boundary_issues.append("missing_competitor_research_evidence")
            unknown_gap_ids = sorted(set(candidate.competitor_gap_ids) - allowed_gap_ids)
            if unknown_gap_ids:
                raise ProductTechnicalValidationError(
                    "Candidate referenced an unknown competitor opportunity signal.",
                    {
                        "candidate_id": candidate.candidate_id,
                        "unknown_competitor_gap_ids": unknown_gap_ids,
                    },
                )
            event_result = self.event_gate.evaluate(candidate.event_understanding)
            gate_issues = [*boundary_issues, *event_result.issues]
            candidates.append(
                ProductOpportunityCandidate(
                    **candidate.model_dump(mode="python"),
                    gate_status=(
                        CandidateGateStatus.PASSED
                        if not gate_issues
                        else CandidateGateStatus.BLOCKED
                    ),
                    gate_issues=gate_issues,
                )
            )

        advancing = [
            candidate
            for candidate in candidates
            if candidate.gate_status is CandidateGateStatus.PASSED
        ]
        gaps = list(output.portfolio_gaps)
        if len(advancing) < self.TARGET_CANDIDATES:
            gaps.append(
                ProductTechnicalGap(
                    question=(
                        f"还需要哪些证据才能把可晋级候选从 {len(advancing)} 个补足到 "
                        f"{self.TARGET_CANDIDATES} 个？"
                    ),
                    reason="系统不会用固定模板或无证据推测补足候选数量。",
                    required_evidence_types=[
                        "user_event_or_pain_evidence",
                        "competitor_gap_evidence",
                        "context_signal_availability_evidence",
                    ],
                    affected_candidate_ids=[
                        candidate.candidate_id
                        for candidate in candidates
                        if candidate.gate_status is CandidateGateStatus.BLOCKED
                    ],
                )
            )
        gaps = self._unique_gaps(gaps)
        status = (
            ResearchTaskStatus.COMPLETED
            if len(advancing) >= self.TARGET_CANDIDATES
            and handoff.status is ResearchHandoffStatus.READY
            else ResearchTaskStatus.PARTIAL
            if advancing
            else ResearchTaskStatus.BLOCKED
        )
        payload = ProductTechnicalPayload(
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            candidates=candidates,
            portfolio_gaps=gaps,
            coverage=ProductTechnicalCoverage(
                generated_candidate_count=len(candidates),
                advancing_candidate_count=len(advancing),
                cited_user_evidence_count=len(cited & user_ids),
                cited_competitor_evidence_count=len(cited & competitor_ids),
                evidence_context_hash=self._context_hash(context),
                handoff_status=handoff.status,
            ),
        )
        unknowns = list(
            dict.fromkeys(
                [
                    *output.unknowns,
                    *(gap.question for gap in gaps),
                    *user.unknowns,
                    *competitor.unknowns,
                ]
            )
        )
        contradictions = list(dict.fromkeys([*user.contradictions, *competitor.contradictions]))
        return ProductTechnicalArtifact(
            artifact_id="artifact_pending",
            task_id=task.task_id,
            artifact_type=ResearchAgentType.PRODUCT_TECHNICAL.value,
            schema_version="1.0",
            status=status,
            payload=payload,
            evidence_ids=sorted(cited),
            contradictions=contradictions,
            unknowns=unknowns,
            quality_score=self._quality_score(
                generated=len(candidates),
                advancing=len(advancing),
                has_both_boundaries=bool(cited & user_ids and cited & competitor_ids),
                handoff_status=handoff.status,
            ),
            errors=[] if status is not ResearchTaskStatus.BLOCKED else ["NO_ADVANCING_CANDIDATE"],
        ).to_research_artifact()

    @staticmethod
    def _require_ready_handoff(context: AgentContext) -> ResearchHandoff:
        handoff = context.research_handoff
        if handoff is None or not handoff.ready_for_product_technical:
            raise ProductTechnicalValidationError(
                "Product Technical Agent requires a ready ResearchHandoff.",
                {"handoff_status": handoff.status if handoff is not None else None},
            )
        return handoff

    @classmethod
    def _validate_candidate_diversity(cls, output: ProductTechnicalModelOutput) -> None:
        names: set[str] = set()
        event_signatures: set[str] = set()
        for candidate in output.candidates:
            name = cls._normalize(candidate.name)
            event = candidate.event_understanding
            signature = "|".join(
                (
                    cls._normalize(event.base_event.type),
                    cls._normalize(event.event_state.type),
                    cls._normalize(event.inference),
                )
            )
            if name in names or signature in event_signatures:
                raise ProductTechnicalValidationError(
                    "Product Technical output contains duplicate candidates.",
                    {"candidate_id": candidate.candidate_id},
                )
            names.add(name)
            event_signatures.add(signature)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\w]+", "", value.casefold())

    @staticmethod
    def _unique_gaps(gaps: list[ProductTechnicalGap]) -> list[ProductTechnicalGap]:
        by_question: dict[str, ProductTechnicalGap] = {}
        for gap in gaps:
            by_question.setdefault(gap.question.casefold().strip(), gap)
        return list(by_question.values())

    @staticmethod
    def _context_hash(context: AgentContext) -> str:
        if context.evidence_context is not None:
            return context.evidence_context.context_hash
        canonical = json.dumps(
            context.research_handoff.model_dump(mode="json")
            if context.research_handoff is not None
            else {},
            ensure_ascii=False,
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
        has_both_boundaries: bool,
        handoff_status: ResearchHandoffStatus,
    ) -> float:
        score = 20.0
        score += min(generated / cls.TARGET_CANDIDATES, 1.0) * 20
        score += min(advancing / cls.TARGET_CANDIDATES, 1.0) * 40
        score += 15 if has_both_boundaries else 0
        score += 5 if handoff_status is ResearchHandoffStatus.READY else 0
        return round(min(score, 100.0), 2)
