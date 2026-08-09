import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.infrastructure.database.models import (
    CompetitorMaterialSelectionModel,
    EvidenceModel,
    ModelCallModel,
    SearchDiscoveryRunModel,
    SourceAssetModel,
)
from app.main import create_app
from app.sources.search_discovery import (
    SearchDiscoveryProviderCandidate,
    SearchDiscoveryProviderRequest,
    SearchDiscoveryProviderResponse,
    SearchDiscoveryRegistry,
)
from app.sources.web_connector import WebFetchResult


@dataclass
class MaterialSearchConnector:
    provider_id: str = "material-search"
    available: bool = True
    unavailable_reason: str | None = None
    calls: list[SearchDiscoveryProviderRequest] | None = None

    def __post_init__(self) -> None:
        self.calls = []

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse:
        assert self.calls is not None
        self.calls.append(request)
        if "official product" in request.query:
            title = "Ring Battery Doorbell Pro official product page"
            url = "https://ring.example.com/products/battery-doorbell-pro"
        elif "authorized retailer" in request.query:
            title = "Ring Battery Doorbell Pro US retail listing"
            url = "https://shop.example.com/ring-battery-doorbell-pro"
        else:
            title = "Ring Battery Doorbell Pro owner reviews"
            url = "https://reviews.example.com/ring-battery-doorbell-pro"
        return SearchDiscoveryProviderResponse(
            provider_request_id=f"request-{len(self.calls)}",
            candidates=(
                SearchDiscoveryProviderCandidate(
                    title=title,
                    source_url=url,
                    snippet="A search snippet remains candidate-only until authorization.",
                    score=0.9,
                ),
            ),
        )


class MaterialWebConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, source_url: str) -> WebFetchResult:
        self.calls.append(source_url)
        return WebFetchResult(
            requested_url=source_url,
            final_url=source_url,
            media_type="text/html",
            status_code=200,
            body_utf8=(
                b"<html><body><main><h1>Ring Battery Doorbell Pro</h1>"
                b"<p>Public research material supplied after a human authorization gate.</p>"
                b"</main></body></html>"
            ),
            fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
            etag='"material-v1"',
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'material-discovery.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def _project(client: TestClient) -> str:
    created = client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": "What should eufy build next for package security?",
                "category": "smart doorbell",
                "target_user": "US households",
                "region": "US",
                "scenarios": ["front door package"],
            }
        },
    )
    assert created.status_code == 201
    project_id = str(created.json()["project_id"])
    scoped = client.put(
        f"/api/v1/projects/{project_id}/source-requirements/scope",
        json={
            "target_products": [{"brand": "eufy", "model": "E340"}],
            "competitors": [{"brand": "Ring", "model": "Battery Doorbell Pro"}],
            "dimensions": ["official_product", "price_channel", "user_review"],
            "actor": "research-lead",
            "reason": "Confirm exact products and research dimensions.",
        },
    )
    assert scoped.status_code == 200
    return project_id


def _request() -> dict[str, object]:
    return {
        "products": [
            {
                "product_role": "competitor",
                "product": {"brand": "Ring", "model": "Battery Doorbell Pro"},
            }
        ],
        "dimensions": ["official_product", "price_channel", "user_review"],
        "provider_id": "material-search",
        "max_results_per_query": 3,
        "requested_by": "research-lead",
        "purpose": "Discover sources for the confirmed competitor.",
    }


def test_material_discovery_searches_each_dimension_then_onboards_selected_sources(
    tmp_path: Path,
) -> None:
    search = MaterialSearchConnector()
    web = MaterialWebConnector()
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry((search,))
    application.state.web_connector = web

    with TestClient(application) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/competitor-material-discoveries",
            json=_request(),
        )
        body = created.json()
        discovery_id = body["material_discovery_id"]
        source_before = client.get(f"/api/v1/projects/{project_id}/sources")
        candidate_ids = [
            item["search_run"]["candidates"][0]["candidate_id"]
            for item in body["items"]
        ]
        confirmed = client.post(
            f"/api/v1/projects/{project_id}/competitor-material-discoveries/{discovery_id}/decision",
            json={
                "action": "confirm",
                "selected_candidate_ids": candidate_ids,
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "actor": "research-lead",
                "reason": "These public pages may be used for this research project.",
            },
        )
        repeated = client.post(
            f"/api/v1/projects/{project_id}/competitor-material-discoveries/{discovery_id}/decision",
            json={
                "action": "confirm",
                "selected_candidate_ids": candidate_ids,
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "actor": "research-lead",
                "reason": "These public pages may be used for this research project.",
            },
        )
        requirements = client.get(f"/api/v1/projects/{project_id}/source-requirements")
        listed = client.get(
            f"/api/v1/projects/{project_id}/competitor-material-discoveries"
        )

    assert created.status_code == 201
    assert body["status"] == "completed"
    assert body["item_count"] == 3
    assert body["completed_item_count"] == 3
    assert body["candidate_count"] == 3
    assert {item["dimension"] for item in body["items"]} == {
        "official_product",
        "price_channel",
        "user_review",
    }
    assert all(
        item["search_run"]["candidates"][0]["evidence_status"] == "candidate_only"
        for item in body["items"]
    )
    assert source_before.json()["total"] == 0
    assert confirmed.status_code == 201
    assert confirmed.json()["created"] is True
    assert len(confirmed.json()["decision"]["selections"]) == 3
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert listed.json()["total"] == 1
    assert len(search.calls or []) == 3
    assert len(web.calls) == 3
    competitor_materials = [
        item
        for item in requirements.json()["requirements"]
        if item["product_role"] == "competitor" and item["dimension"] is not None
    ]
    assert {item["dimension"] for item in competitor_materials} == {
        "official_product",
        "price_channel",
        "user_review",
    }
    assert all(item["detected_source_asset_ids"] for item in competitor_materials)

    async def audit() -> tuple[int, int, int, int, int]:
        async with application.state.database.session() as session:
            searches = int(
                await session.scalar(select(func.count()).select_from(SearchDiscoveryRunModel))
                or 0
            )
            assets = int(
                await session.scalar(select(func.count()).select_from(SourceAssetModel)) or 0
            )
            selections = int(
                await session.scalar(
                    select(func.count()).select_from(CompetitorMaterialSelectionModel)
                )
                or 0
            )
            evidence = int(
                await session.scalar(select(func.count()).select_from(EvidenceModel)) or 0
            )
            model_calls = int(
                await session.scalar(select(func.count()).select_from(ModelCallModel)) or 0
            )
        return searches, assets, selections, evidence, model_calls

    assert asyncio.run(audit()) == (3, 3, 3, 0, 0)


def test_material_discovery_rejects_out_of_scope_products_and_foreign_candidates(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry(
        (MaterialSearchConnector(),)
    )
    with TestClient(application) as client:
        project_id = _project(client)
        out_of_scope = _request()
        out_of_scope["products"] = [
            {
                "product_role": "competitor",
                "product": {"brand": "Google", "model": "Nest Doorbell"},
            }
        ]
        invalid_product = client.post(
            f"/api/v1/projects/{project_id}/competitor-material-discoveries",
            json=out_of_scope,
        )
        created = client.post(
            f"/api/v1/projects/{project_id}/competitor-material-discoveries",
            json={**_request(), "dimensions": ["official_product"]},
        )
        discovery_id = created.json()["material_discovery_id"]
        invalid_candidate = client.post(
            f"/api/v1/projects/{project_id}/competitor-material-discoveries/{discovery_id}/decision",
            json={
                "action": "confirm",
                "selected_candidate_ids": ["candidate_from_another_run"],
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "actor": "research-lead",
                "reason": "Try a candidate outside this batch.",
            },
        )

    assert invalid_product.status_code == 422
    assert invalid_product.json()["code"] == "COMPETITOR_MATERIAL_PRODUCT_OUT_OF_SCOPE"
    assert invalid_candidate.status_code == 422
    assert invalid_candidate.json()["code"] == "COMPETITOR_MATERIAL_CANDIDATE_NOT_FOUND"
