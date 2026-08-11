import pytest
from pydantic import ValidationError

from app.schemas.evidence import EvidenceStatus
from app.schemas.evidence_retrieval import EvidenceRetrievalQuery


def test_shared_retrieval_accepts_only_agent_eligible_evidence() -> None:
    with pytest.raises(ValidationError, match="agent-eligible"):
        EvidenceRetrievalQuery(
            consumer="red_team",
            statuses=[EvidenceStatus.MOCK],
        )


def test_shared_retrieval_requires_consistent_modes_and_limits() -> None:
    with pytest.raises(ValidationError, match="candidate_limit"):
        EvidenceRetrievalQuery(
            consumer="user_research",
            max_items=20,
            candidate_limit=10,
        )
    with pytest.raises(ValidationError, match="preserve_evidence_order"):
        EvidenceRetrievalQuery(
            consumer="ecosystem_opportunity",
            preserve_evidence_order=True,
        )
    with pytest.raises(ValidationError, match="every ordered evidence"):
        EvidenceRetrievalQuery(
            consumer="ecosystem_opportunity",
            evidence_ids=[f"evidence_{index}" for index in range(3)],
            max_items=1,
            candidate_limit=2,
            preserve_evidence_order=True,
        )
    with pytest.raises(ValidationError, match="require_text_match"):
        EvidenceRetrievalQuery(
            consumer="commercial_evaluation",
            require_text_match=True,
        )


def test_shared_retrieval_rejects_case_insensitive_duplicate_filters() -> None:
    with pytest.raises(ValidationError, match="filters must be unique"):
        EvidenceRetrievalQuery(
            consumer="competitor_research",
            regions=["US", "us"],
        )
