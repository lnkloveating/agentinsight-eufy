from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.competitor_source_onboarding import CompetitorSourceOnboardingCreate


@pytest.mark.parametrize(
    "update",
    [
        {"authorization_basis": "enterprise_authorized"},
        {"authorization_confirmed": False},
        {"authorized_by": "   "},
        {"purpose": "   "},
    ],
)
def test_onboarding_requires_explicit_public_authorization(update: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "artifact_id": "artifact_candidate",
        "authorization_basis": "publicly_available",
        "authorization_confirmed": True,
        "authorized_by": "research-lead",
        "purpose": "Use confirmed public product candidates for research.",
    }
    payload.update(update)

    with pytest.raises(ValidationError):
        CompetitorSourceOnboardingCreate.model_validate(payload)


def test_onboarding_strips_audit_text() -> None:
    payload = CompetitorSourceOnboardingCreate.model_validate(
        {
            "artifact_id": " artifact_candidate ",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": " research-lead ",
            "purpose": " competitor source research ",
        }
    )

    assert payload.artifact_id == "artifact_candidate"
    assert payload.authorized_by == "research-lead"
    assert payload.purpose == "competitor source research"
