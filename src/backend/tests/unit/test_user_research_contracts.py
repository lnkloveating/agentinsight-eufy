import pytest
from pydantic import ValidationError

from app.agents.user_research.contracts import UserPainPoint, UserResearchModelOutput
from app.agents.user_research.validation import (
    UserResearchOutputValidator,
    UserResearchValidationError,
)
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchAgentType,
    ResearchTask,
)


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


def _agent_evidence(
    evidence_id: str,
    *,
    domain: str,
    claim_type: str = "user_opinion",
) -> AgentEvidence:
    return AgentEvidence(
        evidence_id=evidence_id,
        title="Review",
        original_excerpt="The user must inspect the notification manually.",
        claim_type=claim_type,
        status="verified",
        source_type="webpage",
        source_domain=domain,
        confidence=0.9,
        authority_score=0.8,
        recency_score=0.8,
        diversity_score=0.8,
    )


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_user_research",
        project_id="proj_user",
        agent_type=ResearchAgentType.USER_RESEARCH,
        goal="Find evidence-backed user problems.",
    )


def _complete_output() -> UserResearchModelOutput:
    return UserResearchModelOutput.model_validate(
        {
            "summary": "Users manually interpret alerts.",
            "summary_evidence_ids": ["ev_one", "ev_two"],
            "event_chains": [
                {
                    "event": "A package arrives.",
                    "context": "The user is away.",
                    "user_state": "The user cannot confirm package risk.",
                    "current_response": "Open the notification and inspect it.",
                    "evidence_ids": ["ev_one"],
                }
            ],
            "pain_points": [
                {
                    "pain_point_id": "manual_check",
                    "user_expression": "I still check every notification.",
                    "trigger_event": "A package alert arrives.",
                    "context": "The user is away.",
                    "severity": "medium",
                    "frequency_basis": "Two independent cited reviews.",
                    "current_workaround": "Open live view.",
                    "solution_gap": "The notification lacks contextual interpretation.",
                    "confidence": 0.8,
                    "evidence_ids": ["ev_one", "ev_two"],
                }
            ],
            "unmet_needs": [
                {
                    "need_id": "risk_context",
                    "statement": "Users need contextual package risk information.",
                    "desired_outcome": "Know when action is actually required.",
                    "confidence": 0.7,
                    "evidence_ids": ["ev_one", "ev_two"],
                }
            ],
            "sample_biases": [],
            "research_gaps": [],
            "contradictions": [],
            "unknowns": [],
        }
    )


def test_validator_builds_completed_artifact_from_two_user_sources() -> None:
    context = AgentEvidenceContext(
        items=[
            _agent_evidence("ev_one", domain="reviews.example"),
            _agent_evidence("ev_two", domain="community.example"),
        ],
        available_evidence_count=2,
        included_evidence_count=2,
        omitted_evidence_count=0,
        context_hash="a" * 64,
    )

    artifact = UserResearchOutputValidator().validate(
        _task(), context, _complete_output()
    )

    assert artifact.status == "completed"
    assert artifact.evidence_ids == ["ev_one", "ev_two"]
    assert artifact.quality_score == 100
    assert artifact.payload["evidence_coverage"]["independent_domain_count"] == 2


def test_validator_rejects_vendor_claim_as_user_pain_or_unknown_citation() -> None:
    context = AgentEvidenceContext(
        items=[
            _agent_evidence(
                "ev_one", domain="vendor.example", claim_type="vendor_claim"
            ),
            _agent_evidence("ev_two", domain="community.example"),
        ],
        available_evidence_count=2,
        included_evidence_count=2,
        omitted_evidence_count=0,
        context_hash="b" * 64,
    )
    output = _complete_output()
    output.pain_points[0].evidence_ids = ["ev_one"]
    with pytest.raises(UserResearchValidationError, match="user_opinion"):
        UserResearchOutputValidator().validate(_task(), context, output)

    output = _complete_output()
    output.summary_evidence_ids = ["ev_missing"]
    with pytest.raises(UserResearchValidationError, match="未提供"):
        UserResearchOutputValidator().validate(_task(), context, output)
