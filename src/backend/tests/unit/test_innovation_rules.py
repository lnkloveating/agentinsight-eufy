import pytest
from pydantic import ValidationError

from app.domain.innovation import (
    EventUnderstandingGate,
    InnovationPortfolioGate,
    InnovationRuleError,
    InnovationScorer,
)
from app.schemas.innovation import (
    ContextSignal,
    EventReference,
    EventUnderstanding,
    Innovation,
    InnovationScoreInput,
    InnovationStatus,
    ProblemDefinition,
    RedTeamDecision,
    RedTeamReview,
    RedTeamSeverity,
    ScoreComponent,
    ScoreDimension,
    SignalAvailability,
    TargetUser,
)


def _signal(
    signal_type: str,
    availability: SignalAvailability = SignalAvailability.AVAILABLE,
) -> ContextSignal:
    return ContextSignal(
        type=signal_type,
        source=f"source:{signal_type}",
        availability=availability,
        authorization="explicit user authorization",
        freshness="within five minutes",
        latency_ms=200,
        confidence=0.9,
        fallback="return an inconclusive result",
    )


def _event(*signals: ContextSignal) -> EventUnderstanding:
    return EventUnderstanding(
        base_event=EventReference(type="package_delivered", source="doorbell"),
        event_state=EventReference(type="package_still_present", source="doorbell"),
        context_signals=list(signals),
        inference="The package may remain exposed.",
        risk_or_value="Possible weather damage.",
        recommended_action="Ask the resident to review the event.",
    )


def _score_input(evidence_id: str = "ev_valid") -> InnovationScoreInput:
    weight = 1 / len(ScoreDimension)
    return InnovationScoreInput(
        score_breakdown={
            dimension: ScoreComponent(
                score=80,
                weight=weight,
                rationale=f"Rationale for {dimension.value}",
                evidence_ids=[evidence_id],
            )
            for dimension in ScoreDimension
        }
    )


def _innovation(innovation_id: str, status: InnovationStatus) -> Innovation:
    return Innovation(
        innovation_id=innovation_id,
        name=innovation_id,
        status=status,
        target_user=TargetUser(description="Doorbell owner"),
        problem=ProblemDefinition(description="Notifications lack context"),
        event_understanding=_event(_signal("weather"), _signal("package_presence")),
        competitor_gap_ids=[],
        evidence_ids=["ev_valid"],
        score_breakdown={},
        base_score=0,
        final_score=0,
    )


def test_event_understanding_requires_two_distinct_available_signals() -> None:
    passed = EventUnderstandingGate().evaluate(
        _event(_signal("weather"), _signal("package_presence"))
    )
    blocked = EventUnderstandingGate().evaluate(
        _event(
            _signal("weather"),
            _signal("weather", SignalAvailability.SIMULATED),
        )
    )

    assert passed.passed is True
    assert blocked.passed is False
    assert blocked.issues == (
        "context_signals_not_distinct",
        "context_signal_not_available:weather:simulated",
    )


def test_score_is_deterministic_and_requires_allowed_evidence() -> None:
    scorer = InnovationScorer()
    payload = _score_input()

    assert scorer.calculate_base_score(payload, allowed_evidence_ids={"ev_valid"}) == 80
    with pytest.raises(InnovationRuleError) as exc_info:
        scorer.calculate_base_score(payload, allowed_evidence_ids={"ev_other"})
    assert "score_evidence_not_allowed" in str(exc_info.value)


def test_red_team_can_lower_but_not_raise_final_score() -> None:
    payload = _score_input()
    review = RedTeamReview(
        severity=RedTeamSeverity.MEDIUM,
        score_adjustments={ScoreDimension.TECHNICAL_DATA_FEASIBILITY: -40},
        required_actions=["Verify the signal source"],
        decision=RedTeamDecision.REVISE,
    )

    assert InnovationScorer().apply_red_team(
        payload, review, allowed_evidence_ids={"ev_valid"}
    ) == 75

    with pytest.raises(ValidationError):
        RedTeamReview(
            severity=RedTeamSeverity.LOW,
            score_adjustments={ScoreDimension.BUSINESS_VALUE: 5},
            decision=RedTeamDecision.PASS,
        )


def test_portfolio_gate_reports_gap_without_creating_fake_candidates() -> None:
    one_candidate = [_innovation("inv_one", InnovationStatus.RECOMMENDED)]
    result = InnovationPortfolioGate().evaluate(one_candidate)

    assert result.candidate_count == 1
    assert result.ready_for_scenario_approval is False
    assert result.gaps == ["insufficient_candidates:1/3"]
