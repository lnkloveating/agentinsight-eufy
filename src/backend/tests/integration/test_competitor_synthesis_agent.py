import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.application.model_gateway import ModelUsage, ProviderModelRequest, ProviderModelResult
from app.core.config import Settings
from app.infrastructure.database import EvidenceModel, ProjectModel
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext
from tests.research_brief import home_safety_brief

PRODUCT = "Target Doorbell"


class FullCompetitorProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        properties = request.response_schema["properties"]
        if "products" in properties:
            output = self._official_output()
        elif "price_observations" in properties:
            output = self._price_output()
        elif "review_themes" in properties:
            output = self._review_output()
        elif "ecosystem_profiles" in properties:
            output = self._ecosystem_output()
        else:
            assert "product_profiles" in properties
            output = self._synthesis_output()
        return ProviderModelResult(
            output=output,
            usage=ModelUsage(input_tokens=600, output_tokens=300),
            provider_request_id=f"provider-request-{len(self.requests)}",
        )

    @staticmethod
    def _official_output() -> dict[str, object]:
        return {
            "summary": "Official evidence documents package detection.",
            "summary_evidence_ids": ["ev_official"],
            "products": [
                {
                    "scope_label": PRODUCT,
                    "official_name": PRODUCT,
                    "model_numbers": ["MODEL-1"],
                    "facts": [
                        {
                            "fact_id": "fact_package_detection",
                            "fact_type": "capability",
                            "field_name": "package detection",
                            "value": "supported",
                            "qualifiers": {"region": "US"},
                            "confidence": 0.92,
                            "evidence_ids": ["ev_official"],
                        }
                    ],
                    "unknown_fields": [],
                    "evidence_ids": ["ev_official"],
                }
            ],
            "contradictions": [],
            "research_gaps": [],
            "unknowns": [],
        }

    @staticmethod
    def _price_output() -> dict[str, object]:
        return {
            "summary": "Two channels provide bounded price and availability observations.",
            "summary_evidence_ids": ["ev_price", "ev_channel"],
            "price_observations": [
                {
                    "observation_id": "price_us",
                    "scope_label": PRODUCT,
                    "amount": "149.99",
                    "currency": "USD",
                    "price_kind": "regular",
                    "region": "US",
                    "channel_name": "Vendor Store",
                    "seller_name": "Vendor",
                    "variant": "MODEL-1",
                    "promotion_terms": None,
                    "confidence": 0.9,
                    "evidence_ids": ["ev_price"],
                }
            ],
            "channel_observations": [
                {
                    "observation_id": "channel_us",
                    "scope_label": PRODUCT,
                    "channel_name": "Retailer",
                    "seller_name": "Retailer",
                    "region": "US",
                    "availability": "in_stock",
                    "variant": "MODEL-1",
                    "confidence": 0.88,
                    "evidence_ids": ["ev_channel"],
                }
            ],
            "contradictions": [],
            "research_gaps": [],
            "unknowns": [],
        }

    @staticmethod
    def _review_output() -> dict[str, object]:
        return {
            "summary": "Independent reviews repeat delayed package notifications.",
            "summary_evidence_ids": ["ev_review_a", "ev_review_b"],
            "review_themes": [
                {
                    "theme_id": "theme_delayed_alert",
                    "scope_label": PRODUCT,
                    "theme": "delayed package alerts",
                    "sentiment": "negative",
                    "user_expression": "Alerts sometimes arrive after the package is left.",
                    "event_context": "package left at the front door",
                    "user_impact": "the user cannot respond promptly",
                    "user_segment": "doorbell owner",
                    "region": "US",
                    "confidence": 0.84,
                    "evidence_ids": ["ev_review_a", "ev_review_b"],
                }
            ],
            "contradictions": [],
            "sample_limitations": [
                {
                    "scope_label": PRODUCT,
                    "description": "The sample contains two independent public reviews.",
                    "impact": "Prevalence across all owners remains unknown.",
                    "evidence_ids": ["ev_review_a", "ev_review_b"],
                }
            ],
            "research_gaps": [],
            "unknowns": ["Overall prevalence is unknown."],
        }

    @staticmethod
    def _synthesis_output() -> dict[str, object]:
        return {
            "summary": "The product detects packages, while reviews identify alert latency.",
            "summary_evidence_ids": ["ev_official", "ev_review_a", "ev_review_b"],
            "product_profiles": [
                {
                    "scope_label": PRODUCT,
                    "strengths": [
                        {
                            "point_id": "strength_package_detection",
                            "dimension": "official_product",
                            "statement": "Package detection is documented.",
                            "explanation": "The official specialist confirmed the capability.",
                            "confidence": 0.9,
                            "evidence_ids": ["ev_official"],
                        }
                    ],
                    "weaknesses": [
                        {
                            "point_id": "weakness_alert_latency",
                            "dimension": "user_review",
                            "statement": "Delayed alerts are a repeated user friction.",
                            "explanation": "Two independent review sources describe it.",
                            "confidence": 0.82,
                            "evidence_ids": ["ev_review_a", "ev_review_b"],
                        }
                    ],
                    "tradeoffs": [
                        {
                            "point_id": "tradeoff_price",
                            "dimension": "price_channel",
                            "statement": "The observed price is a purchase tradeoff.",
                            "explanation": "The observation is region and time bounded.",
                            "confidence": 0.8,
                            "evidence_ids": ["ev_price"],
                        }
                    ],
                }
            ],
            "comparative_insights": [],
            "opportunity_signals": [
                {
                    "signal_id": "signal_package_risk_context",
                    "scope_labels": [PRODUCT],
                    "statement": "Package-risk context may merit product validation.",
                    "rationale": "Detection exists, but users report delayed response context.",
                    "validation_questions": [
                        "Can event, presence and weather context improve response timing?"
                    ],
                    "evidence_ids": ["ev_official", "ev_review_a", "ev_review_b"],
                }
            ],
            "research_gaps": [],
            "unknowns": [],
        }

    @staticmethod
    def _ecosystem_output() -> dict[str, object]:
        assessments = [
            {
                "assessment_id": "assessment_safety_goal",
                "dimension": "safety_goal_coverage",
                "status": "supported",
                "statement": "Package detection covers one bounded safety goal.",
                "explanation": "Official product evidence documents package detection.",
                "source_dimensions": ["official_product"],
                "evidence_ids": ["ev_official"],
                "confidence": 0.9,
                "unknown_reason": None,
            },
            {
                "assessment_id": "assessment_uncertainty",
                "dimension": "uncertainty_handling",
                "status": "limited",
                "statement": "Review evidence reports delayed alerts in the observed sample.",
                "explanation": "Two independent user-review excerpts report notification lag.",
                "source_dimensions": ["user_review"],
                "evidence_ids": ["ev_review_a", "ev_review_b"],
                "confidence": 0.82,
                "unknown_reason": None,
            },
        ]
        covered = {item["dimension"] for item in assessments}
        dimensions = [
            "safety_goal_coverage",
            "cross_device_orchestration",
            "temporal_state_understanding",
            "active_perception",
            "uncertainty_handling",
            "intervention_ladder",
            "local_cloud_partition",
            "privacy_and_consent",
            "offline_fallback",
            "caregiver_workflow",
            "failure_recovery",
            "business_model",
        ]
        assessments.extend(
            {
                "assessment_id": f"assessment_unknown_{dimension}",
                "dimension": dimension,
                "status": "unknown",
                "statement": f"{dimension} is not established by the bounded evidence.",
                "explanation": "The specialist outputs do not contain a supported conclusion.",
                "source_dimensions": [],
                "evidence_ids": [],
                "confidence": 0,
                "unknown_reason": "No eligible specialist evidence covers this dimension.",
            }
            for dimension in dimensions
            if dimension not in covered
        )
        return {
            "summary": "Bounded evidence covers package detection and observed alert latency.",
            "summary_evidence_ids": ["ev_official", "ev_review_a", "ev_review_b"],
            "ecosystem_profiles": [
                {
                    "ecosystem_label": "eufy Security",
                    "role": "target",
                    "product_scope_labels": [PRODUCT],
                    "assessments": assessments,
                }
            ],
            "comparison_insights": [],
            "opportunity_signals": [
                {
                    "signal_id": "signal_temporal_context",
                    "ecosystem_labels": ["eufy Security"],
                    "gap_dimensions": ["temporal_state_understanding"],
                    "statement": "Continuous package-state understanding merits validation.",
                    "rationale": "Detection and observed alert latency coexist.",
                    "validation_questions": [
                        "Can a cross-time state reduce delayed package responses?"
                    ],
                    "evidence_ids": ["ev_official", "ev_review_a", "ev_review_b"],
                    "hypothesis_status": "requires_ecosystem_opportunity_validation",
                }
            ],
            "research_gaps": [
                {
                    "ecosystem_label": "eufy Security",
                    "dimension": "temporal_state_understanding",
                    "question": "Which evidence establishes cross-time state maintenance?",
                    "reason": "The current product facts cover detection, not state duration.",
                    "severity": "high",
                }
            ],
            "unknowns": ["Comparison ecosystem evidence remains missing."],
        }


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'synthesis.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        model_catalog_json=json.dumps(
            [
                {
                    "model_id": "test:competitor",
                    "provider": "test",
                    "provider_model": "provider-competitor",
                    "display_name": "Competitor integration model",
                    "credential_env": "TEST_COMPETITOR_KEY",
                    "capabilities": ["text", "structured_output"],
                }
            ]
        ),
        openai_compatible_providers_json="[]",
        default_model_id="test:competitor",
    )


def _brief() -> ResearchBrief:
    return home_safety_brief()


def _evidence_context() -> AgentEvidenceContext:
    now = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)

    def evidence(
        evidence_id: str, claim_type: str, domain: str, excerpt: str
    ) -> AgentEvidence:
        return AgentEvidence(
            evidence_id=evidence_id,
            title=evidence_id,
            original_excerpt=excerpt,
            claim_type=claim_type,
            status="verified",
            source_type="webpage",
            source_url=f"https://{domain}/{evidence_id}",
            source_domain=domain,
            product=PRODUCT,
            region="US",
            user_segment="doorbell owner" if claim_type == "user_opinion" else None,
            collected_at=now,
            confidence=0.9,
            authority_score=0.85,
            recency_score=0.85,
            diversity_score=0.8,
        )

    items = [
        evidence("ev_official", "vendor_claim", "vendor.example", "Package detection."),
        evidence("ev_price", "price_observation", "store-a.example", "USD 149.99."),
        evidence("ev_channel", "channel_availability", "store-b.example", "In stock."),
        evidence("ev_review_a", "user_opinion", "review-a.example", "Alert was late."),
        evidence("ev_review_b", "user_opinion", "review-b.example", "Notification lagged."),
    ]
    return AgentEvidenceContext(
        items=items,
        available_evidence_count=len(items),
        included_evidence_count=len(items),
        omitted_evidence_count=0,
        context_hash="b" * 64,
    )


def test_three_specialists_flow_into_product_and_ecosystem_synthesis(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_COMPETITOR_KEY", "test-secret")
    application = create_app(_settings(tmp_path))
    provider = FullCompetitorProvider()
    application.state.model_provider_registry.register(provider)

    with TestClient(application) as client:
        async def arrange() -> None:
            now = datetime.now(UTC)
            async with application.state.database.session() as session:
                session.add(
                    ProjectModel(
                        project_id="project_synthesis",
                        status=ProjectStatus.RESEARCHING,
                        current_stage="parallel_research",
                        progress=30,
                        brief_json=_brief().model_dump(mode="json"),
                        model_selection_json={
                            "default_model_id": "test:competitor",
                            "agent_overrides": {},
                        },
                        created_at=now,
                        updated_at=now,
                    )
                )
                for index, item in enumerate(_evidence_context().items):
                    session.add(
                        EvidenceModel(
                            evidence_id=item.evidence_id,
                            project_id="project_synthesis",
                            collection_job_id=None,
                            source_url=item.source_url,
                            normalized_source_url=item.source_url,
                            source_domain=item.source_domain,
                            source_type=item.source_type,
                            title=item.title,
                            original_excerpt=item.original_excerpt,
                            claim_type=item.claim_type,
                            product=item.product,
                            region=item.region,
                            user_segment=item.user_segment,
                            published_at=item.published_at,
                            collected_at=item.collected_at or now,
                            status=item.status,
                            content_hash=f"{index + 1:064x}",
                            confidence=item.confidence,
                            authority_score=item.authority_score,
                            recency_score=item.recency_score,
                            diversity_score=item.diversity_score,
                        )
                    )
                await session.commit()

        asyncio.run(arrange())
        response = client.post(
            "/api/v1/projects/project_synthesis/agents/competitor-ecosystem"
        )
        assert response.status_code == 200, response.text
        artifact = response.json()
        history_response = client.get(
            "/api/v1/projects/project_synthesis/agents/competitor-ecosystem/artifacts"
        )
        assert history_response.status_code == 200, history_response.text
        assert history_response.json() == [artifact]

        async def read_model_calls() -> list[object]:
            async with application.state.database.session() as session:
                runs = await ProjectRepository(session).list_agent_runs("project_synthesis")
                model_calls = await ModelCallRepository(session).list_for_run(
                    runs[0].agent_run_id
                )
            return list(model_calls)

        model_calls = asyncio.run(read_model_calls())

    assert artifact["status"] == "partial"
    assert artifact["agent_run_id"].startswith("run_")
    assert artifact["version"] == 1
    assert artifact["payload"]["schema_name"] == "competitor_ecosystem_analysis"
    assert artifact["payload"]["synthesis_status"] == "partial"
    assert artifact["payload"]["evidence_audit"]["status"] == "passed_with_gaps"
    assert artifact["payload"]["coverage_matrix"][0]["complete"] is False
    assert artifact["payload"]["coverage_matrix"][1]["unknown_dimension_count"] == 12
    assert artifact["evidence_ids"] == [
        "ev_channel",
        "ev_official",
        "ev_price",
        "ev_review_a",
        "ev_review_b",
    ]
    assert len(provider.requests) == 5
    assert {call.prompt_key for call in model_calls} == {
        "agent:competitor_official_product",
        "agent:competitor_price_channel",
        "agent:competitor_user_review",
        "agent:competitor_synthesis",
        "agent:competitor_ecosystem_analysis",
    }
    assert all(
        "test-secret" not in message.content
        for request in provider.requests
        for message in request.messages
    )
