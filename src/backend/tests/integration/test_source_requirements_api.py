import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.source_requirement_repository import (
    SourceRequirementRepository,
)
from app.main import create_app
from app.sources.web_connector import WebFetchResult
from tests.research_brief import home_safety_brief_payload


class RequirementPageConnector:
    async def fetch(self, source_url: str) -> WebFetchResult:
        slug = source_url.rstrip("/").rsplit("/", maxsplit=1)[-1]
        return WebFetchResult(
            requested_url=source_url,
            final_url=source_url,
            media_type="text/html",
            status_code=200,
            body_utf8=(
                f"<html><body><main><h1>{slug}</h1>"
                f"<p>Authorized source content for {slug}; USD 199.99; in stock.</p>"
                "</main></body></html>"
            ).encode(),
            fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'requirements.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "brief": home_safety_brief_payload(
                "Which AI-native home-safety ecosystem capabilities should be validated?"
            )
        },
    )
    assert response.status_code == 201
    return str(response.json()["project_id"])


def _add_evidence_source(
    client: TestClient,
    project_id: str,
    *,
    host: str,
    slug: str,
    product: str,
    route: str,
    claim_type: str,
    region: str = "US",
) -> str:
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": f"https://{host}/{slug}",
            "display_name": f"{product} {route}",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": f"{product} {route} research",
        },
    )
    assert registered.status_code == 201
    source_asset_id = str(registered.json()["source_asset"]["source_asset_id"])
    processed = client.post(f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing")
    assert processed.status_code == 200
    assert processed.json()["job"]["status"] == "succeeded"
    analyzed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/analyze",
        json={"use_model": False},
    )
    assert analyzed.status_code == 200
    decided = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/decision",
        json={
            "action": "confirm",
            "selections": [{"route": route, "claim_types": [claim_type]}],
            "actor": "research-lead",
            "reason": "Confirm the authorized source purpose.",
        },
    )
    assert decided.status_code == 200
    fragment = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    ).json()["items"][0]
    promoted = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments/"
        f"{fragment['source_fragment_id']}/evidence",
        json={
            "claim_type": claim_type,
            "product": product,
            "region": region,
            "confidence": 0.9,
            "authority_score": 0.9,
            "recency_score": 0.9,
            "diversity_score": 0.8,
        },
    )
    assert promoted.status_code == 201
    return source_asset_id


def test_requirements_block_unknown_scope_then_become_ready_from_confirmed_evidence(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    application.state.web_connector = RequirementPageConnector()

    with TestClient(application) as client:
        project_id = _create_project(client)
        endpoint = f"/api/v1/projects/{project_id}/source-requirements"

        initial = client.get(endpoint)
        unresolved = client.put(
            f"{endpoint}/scope",
            json={
                "target_products": [{"brand": "eufy", "model": "E340"}],
                "competitors": [{"brand": "Ring", "model": None}],
                "dimensions": ["official_product", "price_channel"],
                "actor": "research-lead",
                "reason": "Start with the known target and unresolved competitor model.",
            },
        )
        scoped = client.put(
            f"{endpoint}/scope",
            json={
                "target_products": [{"brand": "eufy", "model": "E340"}],
                "competitors": [{"brand": "Ring", "model": "D200"}],
                "dimensions": ["official_product", "price_channel"],
                "actor": "research-lead",
                "reason": "Confirm exact target and competitor models.",
            },
        )
        initial_hash = scoped.json()["input_hash"]

        source_ids = {
            _add_evidence_source(
                client,
                project_id,
                host="eufy.example",
                slug="eufy-E340-official",
                product="eufy E340",
                route="official_product",
                claim_type="product_identity",
            ),
            _add_evidence_source(
                client,
                project_id,
                host="shop-eufy.example",
                slug="eufy-E340-price",
                product="eufy E340",
                route="price_channel",
                claim_type="price_observation",
            ),
            _add_evidence_source(
                client,
                project_id,
                host="ring.example",
                slug="Ring-D200-official",
                product="Ring D200",
                route="official_product",
                claim_type="product_identity",
            ),
        }
        wrong_region_source = _add_evidence_source(
            client,
            project_id,
            host="shop-ring-au.example",
            slug="Ring-D200-price-AU",
            product="Ring D200",
            route="price_channel",
            claim_type="price_observation",
            region="AU",
        )
        region_partial = client.get(endpoint)
        source_ids.add(
            _add_evidence_source(
                client,
                project_id,
                host="shop-ring.example",
                slug="Ring-D200-price",
                product="Ring D200",
                route="price_channel",
                claim_type="price_observation",
            )
        )
        ready = client.get(endpoint)
        missing_project = client.get("/api/v1/projects/proj_missing/source-requirements")

    assert initial.status_code == 200
    assert initial.json()["status"] == "blocked"
    assert initial.json()["scope"] is None
    assert initial.json()["missing_required_count"] == 2
    assert unresolved.status_code == 200
    assert unresolved.json()["status"] == "blocked"
    assert "准确型号" in " ".join(unresolved.json()["missing_actions"])
    assert scoped.status_code == 200
    assert scoped.json()["status"] == "partial"
    assert scoped.json()["required_count"] == 6
    assert region_partial.json()["status"] == "partial"
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["region"] == "US"
    assert body["required_count"] == 6
    assert body["satisfied_required_count"] == 6
    assert body["missing_required_count"] == 0
    assert body["missing_actions"] == []
    assert body["unassigned_source_asset_ids"] == [wrong_region_source]
    assert body["input_hash"] != initial_hash
    assert {
        asset_id
        for requirement in body["requirements"]
        for asset_id in requirement["matched_source_asset_ids"]
    } == source_ids
    assert missing_project.status_code == 404

    async def audit() -> tuple[int, list[str]]:
        async with application.state.database.session() as session:
            scope = await SourceRequirementRepository(session).get_scope(project_id)
            events = await ProjectRepository(session).list_events(project_id, limit=100)
        assert scope is not None
        return len(scope.competitors_json), [event.event_type for event in events]

    competitor_count, event_types = asyncio.run(audit())
    assert competitor_count == 1
    assert event_types.count("source_requirement_scope_updated") == 2


def test_failed_core_source_is_reported_as_blocked_with_recovery_action(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    application.state.web_connector = None

    with TestClient(application) as client:
        project_id = _create_project(client)
        endpoint = f"/api/v1/projects/{project_id}/source-requirements"
        scope = client.put(
            f"{endpoint}/scope",
            json={
                "target_products": [{"brand": "eufy", "model": "E340"}],
                "competitors": [{"brand": "Ring", "model": "D200"}],
                "dimensions": ["official_product"],
                "actor": "research-lead",
                "reason": "Check unavailable source recovery guidance.",
            },
        )
        assert scope.status_code == 200
        registered = client.post(
            f"/api/v1/projects/{project_id}/sources/links",
            json={
                "source_url": "https://ring.example/Ring-D200-official",
                "display_name": "Ring D200 official product page",
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "authorized_by": "research-team",
                "purpose": "Ring D200 official product research",
            },
        )
        source_asset_id = registered.json()["source_asset"]["source_asset_id"]
        processing = client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
        )
        assessment = client.get(endpoint)

    assert processing.status_code == 200
    assert processing.json()["job"]["status"] == "blocked"
    competitor_official = next(
        item
        for item in assessment.json()["requirements"]
        if item["requirement_key"] == "material.official_product.competitor"
    )
    assert competitor_official["status"] == "blocked"
    assert competitor_official["detected_source_asset_ids"] == [source_asset_id]
    assert competitor_official["matched_evidence_ids"] == []
    assert "重试" in " ".join(competitor_official["recommended_actions"])
