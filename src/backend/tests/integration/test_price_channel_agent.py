import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.competitor import PriceChannelEvidenceContextBuilder
from app.application.model_gateway import ModelUsage, ProviderModelRequest, ProviderModelResult
from app.application.runtime import AgentRuntimeGateway
from app.core.config import Settings
from app.infrastructure.database.a2a_repository import A2ATaskRepository
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.sources.web_connector import WebFetchResult
from app.workflows.contracts import (
    AgentContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)
from tests.research_brief import home_safety_brief, home_safety_brief_payload


class PricePageConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, source_url: str) -> WebFetchResult:
        self.calls.append(source_url)
        return WebFetchResult(
            requested_url=source_url,
            final_url="https://retailer.example/products/target-doorbell",
            media_type="text/html",
            status_code=200,
            body_utf8=(
                b"<html><body><main>"
                b"<p>Target Doorbell MODEL-1 regular price is USD 149.99 in the US.</p>"
                b"<p>Sold by Authorized Retailer and explicitly marked in stock.</p>"
                b"</main></body></html>"
            ),
            fetched_at=datetime(2026, 8, 9, 10, 30, tzinfo=UTC),
        )


class PriceChannelProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.evidence_ids: list[str] = []
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        price, channel = self.evidence_ids
        return ProviderModelResult(
            output={
                "summary": "授权零售页记录了该产品在美国的价格与库存观察。",
                "summary_evidence_ids": [price, channel],
                "price_observations": [
                    {
                        "observation_id": "price_target_retailer_us",
                        "scope_label": "Target Doorbell",
                        "amount": "149.99",
                        "currency": "USD",
                        "price_kind": "regular",
                        "region": "US",
                        "channel_name": "Authorized Retailer",
                        "seller_name": "Authorized Retailer",
                        "variant": "MODEL-1",
                        "promotion_terms": None,
                        "confidence": 0.9,
                        "evidence_ids": [price],
                    }
                ],
                "channel_observations": [
                    {
                        "observation_id": "channel_target_retailer_us",
                        "scope_label": "Target Doorbell",
                        "channel_name": "Authorized Retailer",
                        "seller_name": "Authorized Retailer",
                        "region": "US",
                        "availability": "in_stock",
                        "variant": "MODEL-1",
                        "confidence": 0.88,
                        "evidence_ids": [channel],
                    }
                ],
                "contradictions": [],
                "research_gaps": [],
                "unknowns": [],
            },
            usage=ModelUsage(input_tokens=700, output_tokens=320),
            provider_request_id="price-channel-provider-request",
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        model_catalog_json=json.dumps(
            [
                {
                    "model_id": "test:price-model",
                    "provider": "test",
                    "provider_model": "provider-price-model",
                    "display_name": "Price channel test model",
                    "credential_env": "TEST_PRICE_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                }
            ]
        ),
        openai_compatible_providers_json=json.dumps(
            [{"provider_id": "test", "base_url": "https://model.invalid/v1"}]
        ),
        default_model_id="test:price-model",
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "source-processing"),
    )


def _approve_project(client: TestClient) -> str:
    created = client.post(
        "/api/v1/projects",
        json={
            "brief": home_safety_brief_payload(
                "What are the authorized US ecosystem price and channel observations?"
            )
        },
    )
    assert created.status_code == 201
    project = created.json()
    approved = client.post(
        f"/api/v1/projects/{project['project_id']}/decisions",
        json={
            "decision_id": project["pending_decision"]["decision_id"],
            "action": "approve",
            "reason": "The product, region and authorized source policy are explicit.",
            "actor": "research-lead",
        },
    )
    assert approved.status_code == 202
    return str(project["project_id"])


def _ingest_price_page(client: TestClient, project_id: str) -> list[str]:
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "https://retailer.example/products/target-doorbell",
            "display_name": "Authorized US price channel page",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "US price retail channel and availability research",
        },
    )
    assert registered.status_code == 201
    source_asset_id = registered.json()["source_asset"]["source_asset_id"]
    processed = client.post(f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing")
    assert processed.status_code == 200
    assert processed.json()["job"]["status"] == "succeeded"
    analyzed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/analyze",
        json={"use_model": False},
    )
    assert analyzed.status_code == 200
    confirmed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/decision",
        json={
            "action": "confirm",
            "selections": [
                {
                    "route": "price_channel",
                    "claim_types": ["price_observation", "channel_availability"],
                }
            ],
            "actor": "research-lead",
            "reason": "This authorized retail page contains explicit price and stock text.",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed_routes"] == ["price_channel"]
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    ).json()["items"]
    assert len(fragments) == 2

    evidence_ids: list[str] = []
    for fragment, claim_type in zip(
        fragments, ["price_observation", "channel_availability"], strict=True
    ):
        promoted = client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}"
            f"/fragments/{fragment['source_fragment_id']}/evidence",
            json={
                "claim_type": claim_type,
                "product": "Target Doorbell",
                "region": "US",
                "confidence": 0.9,
                "authority_score": 0.85,
                "recency_score": 0.9,
                "diversity_score": 0.6,
            },
        )
        assert promoted.status_code == 201
        evidence_ids.append(str(promoted.json()["evidence"]["evidence_id"]))
    return evidence_ids


def test_authorized_price_page_flows_to_bound_a2a_specialist(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_PRICE_MODEL_KEY", "test-secret")
    application = create_app(_settings(tmp_path))
    connector = PricePageConnector()
    provider = PriceChannelProvider()
    application.state.web_connector = connector
    application.state.model_provider_registry.register(provider, replace=True)

    with TestClient(application) as client:
        project_id = _approve_project(client)
        provider.evidence_ids = _ingest_price_page(client, project_id)

        async def run_price_research() -> tuple[object, object, object]:
            evidence_context = await PriceChannelEvidenceContextBuilder(
                application.state.database,
                max_items=20,
                max_excerpt_chars=3_000,
                max_total_chars=20_000,
            ).build(project_id, region="US")
            task = ResearchTask(
                task_id="task_competitor_price_e2e",
                project_id=project_id,
                agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
                goal="Create evidence-backed price channel intelligence.",
                scope={"target_product": "Target Doorbell"},
                evidence_rules=EvidenceRules(
                    citation_required=True, minimum_independent_domains=1
                ),
                budget=ResearchBudget(max_pages=20, deadline_seconds=120),
            )
            artifact = await AgentRuntimeGateway(
                application.state.database,
                application.state.agent_registry,
                application.state.event_broker,
                "trace_price_e2e",
            ).execute(
                task,
                AgentContext(
                    project_id=project_id,
                    brief=home_safety_brief(),
                    iteration=0,
                    evidence_context=evidence_context,
                ),
            )
            async with application.state.database.session() as session:
                a2a_tasks = await A2ATaskRepository(session).list_for_parent(
                    project_id, task.task_id
                )
                runs = await ProjectRepository(session).list_agent_runs(project_id)
                competitor_run = next(run for run in runs if run.task_id == task.task_id)
                model_calls = await ModelCallRepository(session).list_for_run(
                    competitor_run.agent_run_id
                )
            return artifact, a2a_tasks, model_calls

        artifact, raw_tasks, raw_calls = asyncio.run(run_price_research())

    tasks = list(raw_tasks)
    calls = list(raw_calls)
    price_task = next(item for item in tasks if item.specialist_type == "price_channel")
    official_task = next(item for item in tasks if item.specialist_type == "official_product")
    user_task = next(item for item in tasks if item.specialist_type == "user_review")
    assert artifact.status == "blocked"
    assert artifact.payload["schema_name"] == "competitor_ecosystem_analysis"
    assert artifact.payload["synthesis_status"] == "blocked"
    assert price_task.status == "completed"
    assert official_task.status == "blocked"
    assert user_task.status == "blocked"
    payload = price_task.output_json["structured_payload"]
    assert payload["schema_name"] == "price_channel_intelligence"
    assert payload["price_observations"][0]["amount"] == "149.99"
    assert payload["price_observations"][0]["observed_to"]
    assert price_task.output_json["evidence_ids"] == sorted(provider.evidence_ids)
    assert connector.calls == ["https://retailer.example/products/target-doorbell"]
    assert len(provider.requests) == 1
    assert all(
        evidence_id in provider.requests[0].messages[1].content
        for evidence_id in provider.evidence_ids
    )
    assert "test-secret" not in provider.requests[0].messages[1].content
    assert len(calls) == 1
    assert calls[0].prompt_key == "agent:competitor_price_channel"
