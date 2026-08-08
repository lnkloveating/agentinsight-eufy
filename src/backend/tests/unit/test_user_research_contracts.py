import pytest
from pydantic import ValidationError

from app.agents.user_research.contracts import UserPainPoint, UserResearchModelOutput


def test_user_research_output_collects_every_nested_citation() -> None:
    output = UserResearchModelOutput.model_validate(
        {
            "summary": "Users still make the final risk decision.",
            "summary_evidence_ids": ["ev_summary"],
            "event_chains": [
                {
                    "event": "A package is delivered.",
                    "context": "Nobody is home.",
                    "user_state": "The package remains exposed.",
                    "current_response": "The user checks a notification.",
                    "evidence_ids": ["ev_event"],
                }
            ],
            "pain_points": [],
            "unmet_needs": [],
            "sample_biases": [],
            "research_gaps": [],
            "contradictions": [
                {
                    "statement": "Sources disagree on notification latency.",
                    "evidence_ids": ["ev_a", "ev_b"],
                }
            ],
            "unknowns": [],
        }
    )

    assert output.cited_evidence_ids() == {
        "ev_summary",
        "ev_event",
        "ev_a",
        "ev_b",
    }


def test_user_research_finding_rejects_duplicate_or_missing_citations() -> None:
    payload = {
        "pain_point_id": "pain_one",
        "user_expression": "I still have to inspect every alert.",
        "trigger_event": "The doorbell detects motion.",
        "context": "The user is away.",
        "severity": "medium",
        "frequency_basis": "One cited review.",
        "current_workaround": "Open the live view.",
        "solution_gap": "The alert lacks contextual interpretation.",
        "confidence": 0.6,
        "evidence_ids": [],
    }
    with pytest.raises(ValidationError):
        UserPainPoint.model_validate(payload)

    payload["evidence_ids"] = ["ev_one", "ev_one"]
    with pytest.raises(ValidationError, match="evidence_ids must be unique"):
        UserPainPoint.model_validate(payload)
