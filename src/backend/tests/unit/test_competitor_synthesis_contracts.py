import pytest
from pydantic import ValidationError

from app.agents.competitor.synthesis_contracts import (
    CompetitorSynthesisModelOutput,
    HypothesisStatus,
)


def test_opportunity_signal_is_forced_to_remain_an_unvalidated_hypothesis() -> None:
    output = CompetitorSynthesisModelOutput.model_validate(
        {
            "summary": "Evidence-backed summary.",
            "summary_evidence_ids": ["ev_official"],
            "product_profiles": [],
            "comparative_insights": [],
            "opportunity_signals": [
                {
                    "signal_id": "signal_package_context",
                    "scope_labels": ["Target Doorbell"],
                    "statement": "Package context may merit further validation.",
                    "rationale": "Current evidence shows a capability and a user friction.",
                    "validation_questions": ["Is the event frequent enough?"],
                    "evidence_ids": ["ev_official", "ev_review"],
                }
            ],
            "research_gaps": [],
            "unknowns": [],
        }
    )

    assert (
        output.opportunity_signals[0].hypothesis_status
        is HypothesisStatus.REQUIRES_PRODUCT_AGENT_VALIDATION
    )


def test_duplicate_synthesis_evidence_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="evidence_ids must be unique"):
        CompetitorSynthesisModelOutput.model_validate(
            {
                "summary": "Summary.",
                "summary_evidence_ids": ["ev_1", "ev_1"],
                "product_profiles": [],
                "comparative_insights": [],
                "opportunity_signals": [],
                "research_gaps": [],
                "unknowns": [],
            }
        )
