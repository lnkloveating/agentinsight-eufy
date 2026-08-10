import pytest
from pydantic import ValidationError

from app.schemas.project import ResearchBrief
from tests.research_brief import home_safety_brief_payload


def test_ai_native_home_safety_brief_exposes_ecosystem_safety_boundaries() -> None:
    brief = ResearchBrief.model_validate(home_safety_brief_payload())

    assert brief.research_scope.value == "home_safety_ecosystem"
    assert brief.target_ecosystems == ["eufy Security"]
    assert brief.primary_market == "US"
    assert brief.privacy_boundary.raw_media_allowed is False
    assert brief.intervention_boundary.high_impact_action_requires_human_approval is True
    assert "ecosystem_opportunity_portfolio" in {
        deliverable.value for deliverable in brief.deliverables
    }


@pytest.mark.parametrize(
    "legacy_field,legacy_value",
    [
        ("category", "smart doorbell"),
        ("target_user", "US households"),
        ("region", "US"),
        ("scenarios", ["package delivery"]),
        ("constraints", ["must be a doorbell"]),
        ("focus_dimensions", ["single-product features"]),
    ],
)
def test_legacy_single_product_brief_fields_are_rejected(
    legacy_field: str,
    legacy_value: object,
) -> None:
    payload = home_safety_brief_payload()
    payload[legacy_field] = legacy_value

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ResearchBrief.model_validate(payload)


def test_target_and_comparison_ecosystems_cannot_overlap() -> None:
    payload = home_safety_brief_payload(
        target_ecosystems=["eufy Security"],
        comparison_ecosystems=["EUFY SECURITY"],
    )

    with pytest.raises(ValidationError, match="must not overlap"):
        ResearchBrief.model_validate(payload)


def test_high_impact_actions_always_require_human_approval() -> None:
    payload = home_safety_brief_payload()
    payload["intervention_boundary"]["high_impact_action_requires_human_approval"] = False

    with pytest.raises(ValidationError):
        ResearchBrief.model_validate(payload)


def test_duplicate_or_blank_scope_values_are_rejected() -> None:
    duplicate = home_safety_brief_payload(markets=["US", " us "])
    blank = home_safety_brief_payload(safety_goals=["持续理解家庭安全状态", " "])

    with pytest.raises(ValidationError, match="must not contain duplicates"):
        ResearchBrief.model_validate(duplicate)
    with pytest.raises(ValidationError, match="must not contain blank values"):
        ResearchBrief.model_validate(blank)
