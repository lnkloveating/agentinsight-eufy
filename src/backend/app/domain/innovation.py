"""候选场景的事件理解、评分、红队和组合晋级规则。"""

from dataclasses import dataclass

from app.schemas.innovation import (
    EventUnderstanding,
    Innovation,
    InnovationPortfolioGateResult,
    InnovationScoreInput,
    InnovationStatus,
    RedTeamReview,
    ScoreDimension,
    SignalAvailability,
)

REQUIRED_SCORE_DIMENSIONS = frozenset(ScoreDimension)


class InnovationRuleError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = tuple(issues)


@dataclass(frozen=True, slots=True)
class EventUnderstandingGateResult:
    passed: bool
    issues: tuple[str, ...]


class EventUnderstandingGate:
    """只有可获得且来源各异的上下文信号才能进入技术评估。"""

    def evaluate(self, event: EventUnderstanding) -> EventUnderstandingGateResult:
        issues: list[str] = []
        signal_types = [signal.type.casefold() for signal in event.context_signals]
        if len(set(signal_types)) < 2:
            issues.append("context_signals_not_distinct")

        for signal in event.context_signals:
            if signal.availability is not SignalAvailability.AVAILABLE:
                issues.append(
                    f"context_signal_not_available:{signal.type}:{signal.availability.value}"
                )
        return EventUnderstandingGateResult(passed=not issues, issues=tuple(issues))


class InnovationScorer:
    """由结构化分项确定性计算基础分和红队调整分。"""

    def calculate_base_score(
        self,
        payload: InnovationScoreInput,
        *,
        allowed_evidence_ids: set[str],
    ) -> float:
        issues = self._validate_breakdown(payload, allowed_evidence_ids)
        if issues:
            raise InnovationRuleError(issues)
        return round(
            sum(
                component.score * component.weight for component in payload.score_breakdown.values()
            ),
            2,
        )

    def apply_red_team(
        self,
        payload: InnovationScoreInput,
        review: RedTeamReview,
        *,
        allowed_evidence_ids: set[str],
    ) -> float:
        self.calculate_base_score(payload, allowed_evidence_ids=allowed_evidence_ids)
        final_score = 0.0
        for dimension, component in payload.score_breakdown.items():
            adjustment = review.score_adjustments.get(dimension, 0.0)
            adjusted_score = min(100.0, max(0.0, component.score + adjustment))
            final_score += adjusted_score * component.weight
        return round(final_score, 2)

    @staticmethod
    def _validate_breakdown(
        payload: InnovationScoreInput,
        allowed_evidence_ids: set[str],
    ) -> list[str]:
        issues: list[str] = []
        dimensions = set(payload.score_breakdown)
        for missing in sorted(REQUIRED_SCORE_DIMENSIONS - dimensions, key=str):
            issues.append(f"missing_score_dimension:{missing.value}")
        for unexpected in sorted(dimensions - REQUIRED_SCORE_DIMENSIONS, key=str):
            issues.append(f"unexpected_score_dimension:{unexpected}")

        weight_total = sum(component.weight for component in payload.score_breakdown.values())
        if abs(weight_total - 1.0) > 0.0001:
            issues.append(f"score_weights_must_sum_to_one:{weight_total:.6f}")

        for dimension, component in payload.score_breakdown.items():
            invalid_ids = sorted(set(component.evidence_ids) - allowed_evidence_ids)
            if invalid_ids:
                issues.append(
                    f"score_evidence_not_allowed:{dimension.value}:{','.join(invalid_ids)}"
                )
        return issues


class InnovationPortfolioGate:
    """不补造候选，只报告候选数量和未完成红队流程的缺口。"""

    def __init__(self, minimum_candidates: int = 3) -> None:
        self.minimum_candidates = minimum_candidates

    def evaluate(self, innovations: list[Innovation]) -> InnovationPortfolioGateResult:
        gaps: list[str] = []
        if len(innovations) < self.minimum_candidates:
            gaps.append(f"insufficient_candidates:{len(innovations)}/{self.minimum_candidates}")

        resolved_statuses = {InnovationStatus.RECOMMENDED, InnovationStatus.REJECTED}
        unresolved = [
            innovation.innovation_id
            for innovation in innovations
            if innovation.status not in resolved_statuses
        ]
        if unresolved:
            gaps.append(f"unresolved_red_team_reviews:{','.join(sorted(unresolved))}")
        if innovations and not any(
            innovation.status is InnovationStatus.RECOMMENDED for innovation in innovations
        ):
            gaps.append("no_recommended_candidate")

        return InnovationPortfolioGateResult(
            candidate_count=len(innovations),
            minimum_candidates=self.minimum_candidates,
            ready_for_scenario_approval=not gaps,
            gaps=gaps,
        )
