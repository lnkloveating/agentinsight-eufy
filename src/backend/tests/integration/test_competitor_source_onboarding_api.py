import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.competitor.discovery_contracts import (
    CompetitorDiscoveryInputContext,
    CompetitorDiscoveryModelOutput,
)
from app.agents.competitor.discovery_validation import CompetitorDiscoveryOutputValidator
from app.application.runtime import AgentInvocation, AgentRegistry
from app.core.config import Settings
from app.infrastructure.database.models import SourceAssetModel
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.sources.search_discovery import (
    SearchDiscoveryProviderCandidate,
    SearchDiscoveryProviderRequest,
    SearchDiscoveryProviderResponse,
    SearchDiscoveryRegistry,
)
from app.sources.web_connector import WebConnectorError, WebFetchResult
from app.workflows.contracts import ResearchAgentType
from tests.research_brief import home_safety_brief_payload


@dataclass
class OnboardingSearchConnector:
    provider_id: str = "onboarding-search"
    available: bool = True
    unavailable_reason: str | None = None

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse:
        del request
        return SearchDiscoveryProviderResponse(
            provider_request_id="onboarding-search-request",
            candidates=(
                SearchDiscoveryProviderCandidate(
                    title="Ring Battery Doorbell Pro",
                    source_url="https://ring.example/products/battery-doorbell-pro?utm_source=test",
                    snippet="Ring Battery Doorbell Pro official product candidate.",
                    score=0.94,
                ),
                SearchDiscoveryProviderCandidate(
                    title="Google Nest Doorbell Wired 2nd Gen",
                    source_url="https://store.google.example/nest-doorbell-wired-2",
                    snippet="Google Nest Doorbell Wired 2nd Gen product candidate.",
                    score=0.9,
                ),
            ),
        )


class OnboardingDiscoveryAdapter:
    adapter_type = "test_onboarding_discovery"

    async def execute(self, invocation: AgentInvocation) -> object:
        context = CompetitorDiscoveryInputContext.model_validate(
            invocation.task.scope["discovery_context"]
        )
        by_title = {item.title: item.candidate_id for item in context.candidates}
        output = CompetitorDiscoveryModelOutput.model_validate(
            {
                "summary": "识别出两个等待确认的准确竞品型号。",
                "proposals": [
                    {
                        "brand": "Ring",
                        "model": "Battery Doorbell Pro",
                        "variant": None,
                        "category": "smart doorbell",
                        "candidate_ids": [by_title["Ring Battery Doorbell Pro"]],
                        "comparison_dimensions": ["category_fit", "use_case"],
                        "reason": "候选文本明确包含准确品牌和型号。",
                        "confidence": 0.94,
                        "uncertainties": [],
                    },
                    {
                        "brand": "Google Nest",
                        "model": "Doorbell Wired 2nd Gen",
                        "variant": None,
                        "category": "smart doorbell",
                        "candidate_ids": [
                            by_title["Google Nest Doorbell Wired 2nd Gen"]
                        ],
                        "comparison_dimensions": ["category_fit", "form_factor"],
                        "reason": "候选文本明确包含准确品牌和型号。",
                        "confidence": 0.9,
                        "uncertainties": [],
                    },
                ],
                "excluded_candidates": [],
                "research_gaps": [],
                "unknowns": [],
            }
        )
        return CompetitorDiscoveryOutputValidator().validate(
            invocation.task, context, output
        )


class OnboardingWebConnector:
    def __init__(self, *, failing_domain: str | None = None) -> None:
        self.failing_domain = failing_domain
        self.calls: list[str] = []

    async def fetch(self, source_url: str) -> WebFetchResult:
        self.calls.append(source_url)
        if self.failing_domain is not None and self.failing_domain in source_url:
            raise WebConnectorError(
                "WEB_FETCH_TIMEOUT",
                "The webpage fetch timed out.",
                blocked=False,
                retryable=True,
            )
        product_name = (
            "Google Nest Doorbell Wired 2nd Gen"
            if "google" in source_url
            else "Ring Battery Doorbell Pro"
        )
        return WebFetchResult(
            requested_url=source_url,
            final_url=source_url,
            media_type="text/html",
            status_code=200,
            body_utf8=(
                f"<html><body><main><h1>{product_name}</h1>"
                "<p>Official public product information for research.</p>"
                "</main></body></html>"
            ).encode(),
            fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
            etag='"onboarding-v1"',
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'source-onboarding.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def _configure(application: object) -> OnboardingWebConnector:
    application.state.search_discovery_registry = SearchDiscoveryRegistry(
        (OnboardingSearchConnector(),)
    )
    registry = AgentRegistry()
    registry.bind(ResearchAgentType.COMPETITOR_RESEARCH, OnboardingDiscoveryAdapter())
    application.state.competitor_discovery_registry = registry
    connector = OnboardingWebConnector()
    application.state.web_connector = connector
    return connector


def _project(
    client: TestClient,
    question: str = "Which home-safety ecosystems should be compared?",
) -> str:
    created = client.post(
        "/api/v1/projects",
        json={
            "brief": home_safety_brief_payload(question)
        },
    )
    assert created.status_code == 201
    project = created.json()
    approved = client.post(
        f"/api/v1/projects/{project['project_id']}/decisions",
        json={
            "decision_id": project["pending_decision"]["decision_id"],
            "action": "approve",
            "reason": "The scope is ready.",
            "actor": "research-lead",
        },
    )
    assert approved.status_code == 202
    scoped = client.put(
        f"/api/v1/projects/{project['project_id']}/source-requirements/scope",
        json={
            "target_products": [{"brand": "eufy", "model": "E340"}],
            "competitors": [],
            "dimensions": ["official_product", "price_channel", "user_review"],
            "actor": "research-lead",
            "reason": "Confirm the exact target.",
        },
    )
    assert scoped.status_code == 200
    return str(project["project_id"])


def _artifact(client: TestClient, project_id: str) -> dict[str, object]:
    search = client.post(
        f"/api/v1/projects/{project_id}/source-discovery/searches",
        json={
            "query": "eufy E340 exact competing doorbell models",
            "intent": "competitor_candidate",
            "provider_id": "onboarding-search",
            "max_results": 5,
            "include_domains": [],
            "exclude_domains": [],
            "requested_by": "research-lead",
            "purpose": "Find exact competitors for confirmation.",
        },
    )
    assert search.status_code == 201
    run = client.post(
        f"/api/v1/projects/{project_id}/agents/competitor-discovery",
        json={
            "search_discovery_run_ids": [search.json()["search_discovery_run_id"]],
            "minimum_candidates": 2,
        },
    )
    assert run.status_code == 200
    return dict(run.json())


def _confirm_ring(
    client: TestClient, project_id: str, artifact: dict[str, object]
) -> dict[str, object]:
    proposals = list(artifact["proposals"])
    ring = next(item for item in proposals if item["brand"] == "Ring")
    decision = client.post(
        f"/api/v1/projects/{project_id}/agents/competitor-discovery/artifacts/"
        f"{artifact['artifact_id']}/decision",
        json={
            "action": "confirm",
            "selected_proposal_ids": [ring["proposal_id"]],
            "actor": "research-lead",
            "reason": "Ring is the selected direct comparison product.",
        },
    )
    assert decision.status_code == 200
    return ring


def _onboarding_payload(artifact_id: object) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "authorization_basis": "publicly_available",
        "authorization_confirmed": True,
        "authorized_by": "research-lead",
        "purpose": "Evaluate confirmed competitor sources.",
    }


def test_confirmed_candidates_onboard_and_automatically_use_web_processing(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    with TestClient(application) as client:
        connector = _configure(application)
        project_id = _project(client)
        artifact = _artifact(client, project_id)
        ring = _confirm_ring(client, project_id, artifact)
        before_sources = client.get(f"/api/v1/projects/{project_id}/sources").json()
        created = client.post(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )
        repeated = client.post(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )
        listed = client.get(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings"
        )
        sources = client.get(f"/api/v1/projects/{project_id}/sources").json()
        evidence = client.get(f"/api/v1/projects/{project_id}/evidence").json()
        requirements = client.get(
            f"/api/v1/projects/{project_id}/source-requirements"
        ).json()

        assert created.status_code == 201
        result = created.json()
        onboarding = result["onboarding"]
        assert result["created"] is True
        assert onboarding["total_item_count"] == 1
        assert onboarding["unique_source_asset_count"] == 1
        assert onboarding["created_source_asset_count"] == 1
        assert onboarding["reused_source_asset_count"] == 0
        assert onboarding["items"][0]["proposal_id"] == ring["proposal_id"]
        assert onboarding["items"][0]["product"] == {
            "brand": "Ring",
            "model": "Battery Doorbell Pro",
            "variant": None,
        }
        source = onboarding["items"][0]["source_asset"]
        assert source["source_url"] == "https://ring.example/products/battery-doorbell-pro"
        assert source["authorization_basis"] == "publicly_available"
        assert "Ring Battery Doorbell Pro" in source["purpose"]
        processing = client.get(
            f"/api/v1/projects/{project_id}/sources/"
            f"{source['source_asset_id']}/processing"
        )
        routing = client.get(
            f"/api/v1/projects/{project_id}/sources/"
            f"{source['source_asset_id']}/routing"
        )

    assert before_sources["total"] == 0
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["onboarding"]["onboarding_id"] == onboarding["onboarding_id"]
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert sources["total"] == 1
    assert processing.status_code == 200
    assert processing.json()["job"]["status"] == "succeeded"
    assert processing.json()["parsed_artifact"]["fragment_count"] > 0
    assert routing.status_code == 200
    assert routing.json()["status"] == "confirmed"
    assert routing.json()["confirmed_routes"] == ["official_product"]
    assert connector.calls == ["https://ring.example/products/battery-doorbell-pro"]
    assert evidence["total"] == 0
    ring_requirements = [
        item
        for item in requirements["requirements"]
        if item.get("product") is not None and item["product"].get("brand") == "Ring"
    ]
    assert ring_requirements
    requirements_by_dimension = {
        item["dimension"]: item for item in ring_requirements
    }
    assert requirements_by_dimension["official_product"]["status"] == "partial"
    assert source["source_asset_id"] in requirements_by_dimension["official_product"][
        "detected_source_asset_ids"
    ]
    assert requirements_by_dimension["price_channel"]["status"] == "missing"
    assert requirements_by_dimension["user_review"]["status"] == "missing"

    async def project_events() -> list[object]:
        async with application.state.database.session() as session:
            return await ProjectRepository(session).list_events(project_id, limit=100)

    events = asyncio.run(project_events())
    event_types = [item.event_type for item in events]
    assert "source_asset_created" in event_types
    assert "competitor_source_onboarding_completed" in event_types
    assert "source_processing_succeeded" in event_types
    assert event_types.count("source_routing_analyzed") == 1
    assert event_types.count("competitor_source_processing_completed") == 1
    completed = next(
        item for item in events if item.event_type == "competitor_source_processing_completed"
    )
    assert completed.data_json["routing_analyzed_count"] == 1
    assert completed.data_json["routing_confirmed_count"] == 1
    assert completed.data_json["routing_failed_count"] == 0


def test_automatic_processing_isolates_one_failed_competitor_source(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    with TestClient(application) as client:
        _configure(application)
        application.state.web_connector = OnboardingWebConnector(
            failing_domain="google.example"
        )
        project_id = _project(client)
        artifact = _artifact(client, project_id)
        proposal_ids = [item["proposal_id"] for item in artifact["proposals"]]
        decision = client.post(
            f"/api/v1/projects/{project_id}/agents/competitor-discovery/artifacts/"
            f"{artifact['artifact_id']}/decision",
            json={
                "action": "confirm",
                "selected_proposal_ids": proposal_ids,
                "actor": "research-lead",
                "reason": "Process both exact comparison products.",
            },
        )
        assert decision.status_code == 200
        created = client.post(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )
        assert created.status_code == 201
        items = created.json()["onboarding"]["items"]
        statuses = {
            item["product"]["brand"]: client.get(
                f"/api/v1/projects/{project_id}/sources/"
                f"{item['source_asset']['source_asset_id']}/processing"
            ).json()["job"]
            for item in items
        }

    assert statuses["Ring"]["status"] == "succeeded"
    assert statuses["Google Nest"]["status"] == "failed"
    assert statuses["Google Nest"]["error_code"] == "WEB_FETCH_TIMEOUT"

    async def processing_events() -> list[dict[str, object]]:
        async with application.state.database.session() as session:
            events = await ProjectRepository(session).list_events(project_id, limit=100)
        return [
            dict(item.data_json)
            for item in events
            if item.event_type == "competitor_source_processing_completed"
        ]

    events = asyncio.run(processing_events())
    assert len(events) == 1
    assert events[0]["claimed_queued_count"] == 2
    assert events[0]["succeeded_count"] == 1
    assert events[0]["failed_count"] == 1
    assert events[0]["routing_analyzed_count"] == 1
    assert events[0]["routing_confirmed_count"] == 1
    assert events[0]["routing_failed_count"] == 0
    assert events[0]["source_requirements_status"] == "partial"
    assert isinstance(events[0]["source_requirements_input_hash"], str)


def test_source_requirements_prefer_exact_onboarding_lineage_over_ambiguous_text(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    with TestClient(application) as client:
        _configure(application)
        project_id = _project(client)
        artifact = _artifact(client, project_id)
        _confirm_ring(client, project_id, artifact)
        created = client.post(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )
        assert created.status_code == 201
        source_asset_id = created.json()["onboarding"]["items"][0]["source_asset"][
            "source_asset_id"
        ]

        async def make_metadata_ambiguous() -> None:
            async with application.state.database.session() as session:
                source = await session.get(SourceAssetModel, source_asset_id)
                assert source is not None
                source.display_name = (
                    "Ring Battery Doorbell Pro and Google Nest Doorbell Wired 2nd Gen"
                )
                source.purpose = (
                    "Compare Ring Battery Doorbell Pro with Google Nest Doorbell Wired 2nd Gen."
                )
                await session.commit()

        asyncio.run(make_metadata_ambiguous())
        scoped = client.put(
            f"/api/v1/projects/{project_id}/source-requirements/scope",
            json={
                "target_products": [{"brand": "eufy", "model": "E340"}],
                "competitors": [
                    {"brand": "Ring", "model": "Battery Doorbell Pro"},
                    {"brand": "Google Nest", "model": "Doorbell Wired 2nd Gen"},
                ],
                "dimensions": ["official_product"],
                "actor": "research-lead",
                "reason": "Verify exact structured product lineage.",
            },
        )

    assert scoped.status_code == 200
    material_requirements = {
        item["product"]["brand"]: item
        for item in scoped.json()["requirements"]
        if item.get("dimension") == "official_product"
        and item.get("product_role") == "competitor"
    }
    assert material_requirements["Ring"]["status"] == "partial"
    assert material_requirements["Ring"]["detected_source_asset_ids"] == [source_asset_id]
    assert material_requirements["Google Nest"]["status"] == "missing"
    assert material_requirements["Google Nest"]["detected_source_asset_ids"] == []


def test_onboarding_requires_confirmed_gate_and_current_scope(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    with TestClient(application) as client:
        _configure(application)
        project_id = _project(client)
        artifact = _artifact(client, project_id)
        pending = client.post(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )
        _confirm_ring(client, project_id, artifact)
        changed_scope = client.put(
            f"/api/v1/projects/{project_id}/source-requirements/scope",
            json={
                "target_products": [{"brand": "eufy", "model": "E340"}],
                "competitors": [{"brand": "Arlo", "model": "Video Doorbell 2K"}],
                "dimensions": ["official_product", "price_channel", "user_review"],
                "actor": "research-lead",
                "reason": "Remove the previously selected competitor.",
            },
        )
        stale = client.post(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )

    assert pending.status_code == 409
    assert pending.json()["code"] == "COMPETITOR_SOURCE_ONBOARDING_CONFIRM_REQUIRED"
    assert changed_scope.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["code"] == "COMPETITOR_SOURCE_ONBOARDING_SCOPE_STALE"


def test_onboarding_reuses_existing_authorized_link_and_is_project_isolated(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    with TestClient(application) as client:
        _configure(application)
        project_id = _project(client)
        other_project_id = _project(client, "Which cameras compete?")
        artifact = _artifact(client, project_id)
        _confirm_ring(client, project_id, artifact)
        existing = client.post(
            f"/api/v1/projects/{project_id}/sources/links",
            json={
                "source_url": "https://ring.example/products/battery-doorbell-pro",
                "display_name": "Existing authorized Ring source",
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "authorized_by": "research-lead",
                "purpose": "Existing manually supplied research source.",
            },
        )
        onboarded = client.post(
            f"/api/v1/projects/{project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )
        cross_project = client.post(
            f"/api/v1/projects/{other_project_id}/competitor-source-onboardings",
            json=_onboarding_payload(artifact["artifact_id"]),
        )
        sources = client.get(f"/api/v1/projects/{project_id}/sources").json()

    assert existing.status_code == 201
    assert onboarded.status_code == 201
    onboarding = onboarded.json()["onboarding"]
    assert onboarding["created_source_asset_count"] == 0
    assert onboarding["reused_source_asset_count"] == 1
    assert onboarding["items"][0]["source_asset"]["source_asset_id"] == (
        existing.json()["source_asset"]["source_asset_id"]
    )
    assert sources["total"] == 1
    assert cross_project.status_code == 404
    assert cross_project.json()["code"] == "COMPETITOR_DISCOVERY_ARTIFACT_NOT_FOUND"
