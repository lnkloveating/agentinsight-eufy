from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.application.fragment_evidence.service import FragmentEvidencePipelineService
from app.schemas.fragment_evidence import (
    FragmentEvidenceBatchCreate,
    FragmentEvidenceDecisionCreate,
)


def test_fragment_evidence_batch_requires_unique_assets() -> None:
    with pytest.raises(ValidationError):
        FragmentEvidenceBatchCreate(
            source_asset_ids=["source_1", "source_1"],
            requested_by="lead",
            purpose="Prepare evidence drafts.",
        )


def test_fragment_evidence_gate_requires_valid_unique_selections() -> None:
    selection = {
        "fragment_evidence_item_id": "fragment_item_1",
        "claim_type": "vendor_claim",
        "published_at": None,
        "user_segment": None,
    }
    with pytest.raises(ValidationError):
        FragmentEvidenceDecisionCreate.model_validate(
            {
                "action": "confirm",
                "selections": [],
                "actor": "lead",
                "reason": "Nothing selected.",
            }
        )
    with pytest.raises(ValidationError):
        FragmentEvidenceDecisionCreate.model_validate(
            {
                "action": "confirm",
                "selections": [selection, selection],
                "actor": "lead",
                "reason": "Duplicate selection.",
            }
        )
    with pytest.raises(ValidationError):
        FragmentEvidenceDecisionCreate.model_validate(
            {
                "action": "confirm",
                "selections": [
                    {
                        **selection,
                        "published_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                    }
                ],
                "actor": "lead",
                "reason": "Future publication date.",
            }
        )


def test_recency_policy_is_deterministic_and_bounded() -> None:
    now = datetime(2026, 8, 9, tzinfo=UTC)

    assert FragmentEvidencePipelineService._recency_score(None, now) == 0.5
    assert FragmentEvidencePipelineService._recency_score(
        datetime(2026, 1, 1, tzinfo=UTC), now
    ) == 0.9
    assert FragmentEvidencePipelineService._recency_score(
        datetime(2020, 1, 1, tzinfo=UTC), now
    ) == 0.4
