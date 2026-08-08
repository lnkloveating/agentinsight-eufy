import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.application.model_gateway import (
    ModelUsage,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.core.config import Settings
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.sources.web_connector import WebFetchResult


class RoutingPageConnector:
    async def fetch(self, source_url: str) -> WebFetchResult:
        return WebFetchResult(
            requested_url=source_url,
            final_url=source_url,
            media_type="text/html",
            status_code=200,
            body_utf8=(
                b"<html><body><main><h1>Doorbell MODEL-1</h1>"
                b"<p>Price USD 199.99. In stock. Specifications and compatibility.</p>"
                b"</main></body></html>"
            ),
            fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        )


class RoutingProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        return ProviderModelResult(
            output={
                "suggestions": [
                    {
                        "route": "official_product",
                        "claim_types": [
                            "vendor_claim",
                            "product_identity",
                            "specification",
                            "compatibility",
                        ],
                        "confidence": 0.94,
                        "reason": "品牌产品路径并包含型号与规格。",
                        "signals": ["product_path", "technical_terms"],
                        "suggested_by": "model",
                    },
                    {
                        "route": "price_channel",
                        "claim_types": [
                            "price_observation",
                            "channel_availability",
                        ],
                        "confidence": 0.92,
                        "reason": "页面包含币种、价格与库存。",
                        "signals": ["currency_price", "availability"],
                        "suggested_by": "model",
                    },
                    {
                        "route": "technical_document",
                        "claim_types": ["specification", "compatibility"],
                        "confidence": 0.9,
                        "reason": "页面包含规格和兼容性字段。",
                        "signals": ["technical_terms"],
                        "suggested_by": "model",
                    },
                ],
                "unknowns": [],
            },
            usage=ModelUsage(input_tokens=500, output_tokens=180),
            provider_request_id="routing-provider-request",
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'routing.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        model_catalog_json=json.dumps(
            [
                {
                    "model_id": "test:routing-model",
                    "provider": "test",
                    "provider_model": "provider-routing-model",
                    "display_name": "Routing test model",
                    "credential_env": "TEST_ROUTING_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                }
            ]
        ),
        openai_compatible_providers_json=json.dumps(
            [{"provider_id": "test", "base_url": "https://model.invalid/v1"}]
        ),
        default_model_id="test:routing-model",
        model_max_retries=0,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def _project(client: TestClient) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": "Which future opportunities exist in home security?",
                "category": "home security",
                "target_user": "North American households",
                "region": "US",
                "scenarios": ["front door package"],
            },
            "model_selection": {"default_model_id": "test:routing-model"},
        },
    )
    assert response.status_code == 201
    return str(response.json()["project_id"])


def _processed_source(client: TestClient, project_id: str) -> str:
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "https://brand.example/products/doorbell",
            "display_name": "Authorized doorbell product page",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "自动识别资料用途",
        },
    )
    assert registered.status_code == 201
    source_asset_id = str(registered.json()["source_asset"]["source_asset_id"])
    processed = client.post(f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing")
    assert processed.status_code == 200
    assert processed.json()["job"]["status"] == "succeeded"
    return source_asset_id


def test_source_routing_analyzes_once_and_requires_no_manual_claim_type(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_ROUTING_MODEL_KEY", "routing-test-secret")
    application = create_app(_settings(tmp_path))
    provider = RoutingProvider()
    application.state.web_connector = RoutingPageConnector()
    application.state.model_provider_registry.register(provider, replace=True)

    with TestClient(application) as client:
        project_id = _project(client)
        source_asset_id = _processed_source(client, project_id)
        endpoint = f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing"

        missing = client.get(endpoint)
        analyzed = client.post(f"{endpoint}/analyze", json={"use_model": True})
        repeated = client.post(f"{endpoint}/analyze", json={"use_model": True})
        evidence = client.get(f"/api/v1/projects/{project_id}/evidence")
        decision = client.post(
            f"{endpoint}/decision",
            json={
                "action": "confirm",
                "selections": [
                    {
                        "route": "official_product",
                        "claim_types": ["vendor_claim", "specification"],
                    },
                    {
                        "route": "price_channel",
                        "claim_types": [
                            "price_observation",
                            "channel_availability",
                        ],
                    },
                ],
                "actor": "research-lead",
                "reason": "确认该资料同时用于官方产品和价格渠道研究。",
            },
        )

    assert missing.status_code == 404
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["status"] == "confirmed"
    assert body["method"] == "hybrid"
    assert set(body["confirmed_routes"]) == {
        "official_product",
        "price_channel",
        "technical_document",
    }
    assert repeated.json()["source_routing_id"] == body["source_routing_id"]
    assert len(provider.requests) == 1
    assert "routing-test-secret" not in provider.requests[0].messages[1].content
    assert evidence.json()["items"] == []  # Routing never promotes facts into Evidence.
    assert decision.status_code == 200
    assert decision.json()["method"] == "manual"
    assert set(decision.json()["confirmed_routes"]) == {
        "official_product",
        "price_channel",
    }

    async def audit() -> tuple[list[object], list[object]]:
        async with application.state.database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs(project_id)
            model_calls = await ModelCallRepository(session).list_for_run(
                next(run.agent_run_id for run in runs if run.agent_type == "source_routing")
            )
        return list(runs), list(model_calls)

    import asyncio

    runs, model_calls = asyncio.run(audit())
    routing_run = next(run for run in runs if run.agent_type == "source_routing")
    assert routing_run.status == "completed"
    assert len(model_calls) == 1
    assert model_calls[0].prompt_key == "agent:source_routing"


def test_source_routing_rejects_unprocessed_source(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    with TestClient(application) as client:
        project_id = _project(client)
        registered = client.post(
            f"/api/v1/projects/{project_id}/sources/links",
            json={
                "source_url": "https://example.com/raw",
                "display_name": "Raw page",
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "authorized_by": "research-team",
                "purpose": "自动识别",
            },
        ).json()
        source_asset_id = registered["source_asset"]["source_asset_id"]
        response = client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/analyze",
            json={"use_model": False},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "SOURCE_ROUTING_REQUIRES_PROCESSED_SOURCE"
