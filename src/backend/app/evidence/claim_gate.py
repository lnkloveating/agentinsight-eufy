"""Claim 与 Evidence 关系的确定性门禁。"""

from dataclasses import dataclass, field

from app.schemas.evidence import ClaimStatus, ClaimType, EvidenceStatus

_CITATION_REQUIRED_TYPES = {
    ClaimType.FACT,
    ClaimType.USER_OPINION,
    ClaimType.VENDOR_CLAIM,
}
_SUPPORTING_STATUSES = {
    EvidenceStatus.VERIFIED,
    EvidenceStatus.PARTIALLY_VERIFIED,
}


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    evidence_id: str
    project_id: str
    status: EvidenceStatus


@dataclass(frozen=True, slots=True)
class ClaimGateDecision:
    status: ClaimStatus
    eligible_for_factual_use: bool
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    rejected_evidence_ids: dict[str, str] = field(default_factory=dict)


class ClaimGate:
    """只让同项目且已验证的 Evidence 支持事实性 Claim。"""

    def evaluate(
        self,
        *,
        project_id: str,
        claim_type: ClaimType,
        requested_supporting_ids: list[str],
        requested_contradicting_ids: list[str],
        candidates: list[EvidenceCandidate],
    ) -> ClaimGateDecision:
        by_id = {candidate.evidence_id: candidate for candidate in candidates}
        rejected: dict[str, str] = {}

        supporting = self._eligible_ids(project_id, requested_supporting_ids, by_id, rejected)
        contradicting = self._eligible_ids(project_id, requested_contradicting_ids, by_id, rejected)

        if contradicting:
            status = ClaimStatus.DISPUTED
        elif supporting:
            status = ClaimStatus.SUPPORTED
        elif claim_type in _CITATION_REQUIRED_TYPES:
            status = ClaimStatus.MISSING_EVIDENCE
        else:
            status = ClaimStatus.UNKNOWN

        return ClaimGateDecision(
            status=status,
            eligible_for_factual_use=status is ClaimStatus.SUPPORTED,
            supporting_evidence_ids=tuple(supporting),
            contradicting_evidence_ids=tuple(contradicting),
            rejected_evidence_ids=rejected,
        )

    @staticmethod
    def _eligible_ids(
        project_id: str,
        requested_ids: list[str],
        candidates: dict[str, EvidenceCandidate],
        rejected: dict[str, str],
    ) -> list[str]:
        eligible: list[str] = []
        for evidence_id in dict.fromkeys(requested_ids):
            candidate = candidates.get(evidence_id)
            if candidate is None:
                rejected[evidence_id] = "not_found"
            elif candidate.project_id != project_id:
                rejected[evidence_id] = "cross_project"
            elif candidate.status not in _SUPPORTING_STATUSES:
                rejected[evidence_id] = f"status:{candidate.status.value}"
            else:
                eligible.append(evidence_id)
        return eligible
