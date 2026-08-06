from app.evidence.claim_gate import ClaimGate, EvidenceCandidate
from app.schemas.evidence import ClaimStatus, ClaimType, EvidenceStatus


def _candidate(
    evidence_id: str,
    *,
    project_id: str = "proj_one",
    status: EvidenceStatus = EvidenceStatus.VERIFIED,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id=evidence_id,
        project_id=project_id,
        status=status,
    )


def test_verified_same_project_evidence_supports_fact() -> None:
    decision = ClaimGate().evaluate(
        project_id="proj_one",
        claim_type=ClaimType.FACT,
        requested_supporting_ids=["ev_valid"],
        requested_contradicting_ids=[],
        candidates=[_candidate("ev_valid")],
    )

    assert decision.status is ClaimStatus.SUPPORTED
    assert decision.eligible_for_factual_use is True
    assert decision.supporting_evidence_ids == ("ev_valid",)


def test_mock_invalid_unverified_and_cross_project_evidence_are_rejected() -> None:
    decision = ClaimGate().evaluate(
        project_id="proj_one",
        claim_type=ClaimType.FACT,
        requested_supporting_ids=["ev_mock", "ev_invalid", "ev_unverified", "ev_cross"],
        requested_contradicting_ids=[],
        candidates=[
            _candidate("ev_mock", status=EvidenceStatus.MOCK),
            _candidate("ev_invalid", status=EvidenceStatus.INVALID),
            _candidate("ev_unverified", status=EvidenceStatus.UNVERIFIED),
            _candidate("ev_cross", project_id="proj_two"),
        ],
    )

    assert decision.status is ClaimStatus.MISSING_EVIDENCE
    assert decision.eligible_for_factual_use is False
    assert decision.rejected_evidence_ids == {
        "ev_mock": "status:mock",
        "ev_invalid": "status:invalid",
        "ev_unverified": "status:unverified",
        "ev_cross": "cross_project",
    }


def test_valid_contradiction_keeps_claim_disputed() -> None:
    decision = ClaimGate().evaluate(
        project_id="proj_one",
        claim_type=ClaimType.FACT,
        requested_supporting_ids=["ev_support"],
        requested_contradicting_ids=["ev_against"],
        candidates=[_candidate("ev_support"), _candidate("ev_against")],
    )

    assert decision.status is ClaimStatus.DISPUTED
    assert decision.eligible_for_factual_use is False
    assert decision.supporting_evidence_ids == ("ev_support",)
    assert decision.contradicting_evidence_ids == ("ev_against",)
