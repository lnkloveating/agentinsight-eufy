"""用户研究模型输出的确定性证据门禁与质量计算。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.user_research.contracts import (
    FindingSeverity,
    ResearchGap,
    UserResearchArtifact,
    UserResearchEvidenceCoverage,
    UserResearchModelOutput,
    UserResearchPayload,
)
from app.schemas.evidence import EvidenceClaimType
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)


@dataclass(frozen=True)
class UserResearchValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class UserResearchOutputValidator:
    def build_blocked(
        self,
        task: ResearchTask,
        evidence_context: AgentEvidenceContext,
    ) -> ResearchArtifact:
        gap = ResearchGap(
            question="当前项目缺少哪些可用于用户研究的已验证资料？",
            reason="Evidence Lake 中没有 verified 或 partially_verified Evidence。",
            severity=FindingSeverity.HIGH,
            recommended_source_types=["user_reviews", "interviews", "authorized_dataset"],
        )
        payload = UserResearchPayload(
            summary="没有可供用户研究 Agent 使用的有效证据，未调用模型生成结论。",
            summary_evidence_ids=[],
            event_chains=[],
            pain_points=[],
            unmet_needs=[],
            sample_biases=[],
            research_gaps=[gap],
            evidence_coverage=self._coverage(evidence_context, set()),
        )
        return UserResearchArtifact(
            artifact_id="artifact_pending",
            task_id=task.task_id,
            artifact_type=task.agent_type.value,
            schema_version="1.0",
            status=ResearchTaskStatus.BLOCKED,
            payload=payload,
            evidence_ids=[],
            contradictions=[],
            unknowns=[gap.question],
            quality_score=0,
            errors=["USER_RESEARCH_EVIDENCE_REQUIRED"],
        ).to_research_artifact()

    def validate(
        self,
        task: ResearchTask,
        evidence_context: AgentEvidenceContext,
        output: UserResearchModelOutput,
    ) -> ResearchArtifact:
        evidence_by_id = {item.evidence_id: item for item in evidence_context.items}
        cited_ids = output.cited_evidence_ids()
        unsupported = sorted(cited_ids - set(evidence_by_id))
        if unsupported:
            raise UserResearchValidationError(
                "用户研究输出引用了未提供给模型的 Evidence。",
                {"unsupported_evidence_ids": unsupported},
            )

        for pain_point in output.pain_points:
            self._require_user_opinion(
                pain_point.evidence_ids,
                evidence_by_id,
                finding_type="pain_point",
                finding_id=pain_point.pain_point_id,
            )
        for unmet_need in output.unmet_needs:
            self._require_user_opinion(
                unmet_need.evidence_ids,
                evidence_by_id,
                finding_type="unmet_need",
                finding_id=unmet_need.need_id,
            )

        domains = self._independent_sources(cited_ids, evidence_by_id)
        user_opinion_ids = {
            evidence_id
            for evidence_id in cited_ids
            if evidence_by_id[evidence_id].claim_type == EvidenceClaimType.USER_OPINION.value
        }
        high_severity_gap = any(
            gap.severity is FindingSeverity.HIGH for gap in output.research_gaps
        )
        complete_sections = bool(output.event_chains and output.pain_points and output.unmet_needs)
        completed = (
            complete_sections
            and bool(user_opinion_ids)
            and len(domains) >= task.evidence_rules.minimum_independent_domains
            and not high_severity_gap
        )
        status = ResearchTaskStatus.COMPLETED if completed else ResearchTaskStatus.PARTIAL
        coverage = self._coverage(evidence_context, cited_ids)
        coverage = coverage.model_copy(
            update={
                "independent_domain_count": len(domains),
                "user_opinion_evidence_count": len(user_opinion_ids),
            }
        )
        payload = UserResearchPayload(
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            event_chains=output.event_chains,
            pain_points=output.pain_points,
            unmet_needs=output.unmet_needs,
            sample_biases=output.sample_biases,
            research_gaps=output.research_gaps,
            evidence_coverage=coverage,
        )
        contradictions = [
            f"{item.statement} [Evidence: {', '.join(item.evidence_ids)}]"
            for item in output.contradictions
        ]
        unknowns = self._unique([*output.unknowns, *(gap.question for gap in output.research_gaps)])
        return UserResearchArtifact(
            artifact_id="artifact_pending",
            task_id=task.task_id,
            artifact_type=task.agent_type.value,
            schema_version="1.0",
            status=status,
            payload=payload,
            evidence_ids=sorted(cited_ids),
            contradictions=contradictions,
            unknowns=unknowns,
            quality_score=self._quality_score(
                task,
                output,
                domain_count=len(domains),
                has_user_opinion=bool(user_opinion_ids),
            ),
            errors=[],
        ).to_research_artifact()

    @staticmethod
    def _require_user_opinion(
        evidence_ids: list[str],
        evidence_by_id: dict[str, AgentEvidence],
        *,
        finding_type: str,
        finding_id: str,
    ) -> None:
        if any(
            evidence_by_id.get(evidence_id) is not None
            and evidence_by_id[evidence_id].claim_type == EvidenceClaimType.USER_OPINION.value
            for evidence_id in evidence_ids
        ):
            return
        raise UserResearchValidationError(
            "痛点或未满足需求缺少 user_opinion Evidence。",
            {"finding_type": finding_type, "finding_id": finding_id},
        )

    @staticmethod
    def _independent_sources(
        evidence_ids: set[str],
        evidence_by_id: dict[str, AgentEvidence],
    ) -> set[str]:
        sources: set[str] = set()
        for evidence_id in evidence_ids:
            evidence = evidence_by_id[evidence_id]
            if evidence.source_domain:
                sources.add(f"domain:{evidence.source_domain}")
            elif evidence.source_asset_id:
                sources.add(f"asset:{evidence.source_asset_id}")
            else:
                sources.add(f"source_type:{evidence.source_type}")
        return sources

    @staticmethod
    def _coverage(
        evidence_context: AgentEvidenceContext,
        cited_ids: set[str],
    ) -> UserResearchEvidenceCoverage:
        return UserResearchEvidenceCoverage(
            available_evidence_count=evidence_context.available_evidence_count,
            included_evidence_count=evidence_context.included_evidence_count,
            cited_evidence_count=len(cited_ids),
            independent_domain_count=0,
            user_opinion_evidence_count=0,
            context_hash=evidence_context.context_hash,
        )

    @staticmethod
    def _quality_score(
        task: ResearchTask,
        output: UserResearchModelOutput,
        *,
        domain_count: int,
        has_user_opinion: bool,
    ) -> float:
        score = 30.0  # All citations have passed the deterministic gate.
        score += (
            min(
                domain_count / task.evidence_rules.minimum_independent_domains,
                1.0,
            )
            * 20
        )
        score += 20 if has_user_opinion else 0
        score += 10 if output.event_chains else 0
        score += 10 if output.pain_points else 0
        score += 10 if output.unmet_needs else 0
        if any(gap.severity is FindingSeverity.HIGH for gap in output.research_gaps):
            score -= 10
        return max(0.0, min(round(score, 2), 100.0))

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value.strip()))
