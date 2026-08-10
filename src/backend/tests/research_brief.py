"""Canonical AI-native home-safety research scope used by backend tests."""

from typing import Any

from app.schemas.project import ResearchBrief


def home_safety_brief_payload(
    question: str = "研究 eufy AI 原生家庭安防生态机会",
    *,
    target_ecosystems: list[str] | None = None,
    comparison_ecosystems: list[str] | None = None,
    target_users: list[str] | None = None,
    markets: list[str] | None = None,
    risk_scenarios: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Build the only supported research brief shape without legacy product fields."""

    payload: dict[str, Any] = {
        "question": question,
        "research_scope": "home_safety_ecosystem",
        "safety_domains": ["property_security", "personal_safety"],
        "target_ecosystems": target_ecosystems or ["eufy Security"],
        "comparison_ecosystems": comparison_ecosystems or ["Ring", "Google Nest"],
        "target_users": target_users or ["North American households"],
        "markets": markets or ["US"],
        "time_horizon": "next three years",
        "safety_goals": [
            "持续理解家庭安全状态",
            "在证据不足时主动补证并安全降级",
        ],
        "risk_scenarios": risk_scenarios
        or ["package protection", "elder fall-risk prevention"],
        "authorized_signal_types": [
            "visual_event_metadata",
            "motion_event",
            "device_status",
            "user_confirmation",
            "simulated_event",
        ],
        "privacy_boundary": {
            "raw_media_allowed": False,
            "restricted_zones": ["private indoor areas"],
            "retention_policy": "retain only minimum authorized derived event data",
            "external_sharing_allowed": False,
        },
        "intervention_boundary": {
            "allowed_interventions": [
                "continue_observing",
                "request_additional_signal",
                "ask_user",
                "local_prompt",
            ],
            "prohibited_actions": [
                "unlock doors without explicit approval",
                "infer medical diagnoses or protected traits",
            ],
            "high_impact_action_requires_human_approval": True,
        },
        "forbidden_inferences": [
            "medical diagnosis",
            "protected-attribute inference",
            "identity inference without authorization",
        ],
        "evaluation_dimensions": [
            "cross-device perception",
            "state understanding",
            "safe intervention",
            "privacy and fallback",
            "technical verifiability",
        ],
        "validation_expectations": [
            "cover normal, boundary, failure and adversarial scenarios",
            "distinguish simulated events from real evidence",
        ],
        "source_permissions": {
            "public_sources": True,
            "user_uploaded_materials": True,
            "enterprise_internal_materials": False,
            "authorized_household_events": False,
        },
        "deliverables": [
            "ecosystem_opportunity_portfolio",
            "device_capability_gap",
            "policy_dry_run",
            "pilot_recommendation",
        ],
    }
    payload.update(overrides)
    return payload


def home_safety_brief(
    question: str = "研究 eufy AI 原生家庭安防生态机会",
    **overrides: Any,
) -> ResearchBrief:
    return ResearchBrief.model_validate(
        home_safety_brief_payload(question, **overrides)
    )
