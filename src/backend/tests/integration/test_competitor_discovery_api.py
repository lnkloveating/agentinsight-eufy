import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.competitor.discovery_contracts import (
    CompetitorDiscoveryInputContext,
    CompetitorDiscoveryModelOutput,
)
from app.agents.competitor.discovery_validation import CompetitorDiscoveryOutputValidator
from app.application.runtime import AgentInvocation, AgentRegistry
from app.core.config import Settings
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.sources.search_discovery import (
    SearchDiscoveryProviderCandidate,
    SearchDiscoveryProviderRequest,
    SearchDiscoveryProviderResponse,
    SearchDiscoveryRegistry,
)
from app.workflows.contracts import ResearchAgentType
from tests.research_brief import home_safety_brief_payload


@dataclass
class CompetitorSearchConnector:
    provider_id: str = "competitor-search"
    available: bool = True
    unavailable_reason: str | None = None

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse:
        del request
        return SearchDiscoveryProviderResponse(
            provider_request_id="competitor-search-request",
            candidates=(
                SearchDiscoveryProviderCandidate(
                    title="Ring Battery Doorbell Pro",
                    source_url="https://ring.example/battery-doorbell-pro",
                    snippet="Ring Battery Doorbell Pro smart doorbell candidate.",
                    score=0.93,
                ),
                SearchDiscoveryProviderCandidate(
                    title="Google Nest Doorbell Wired 2nd Gen",
                    source_url="https://store.google.example/nest-doorbell-wired-2",
                    snippet="Google Nest Doorbell Wired 2nd Gen candidate.",
                    score=0.88,
                ),
                SearchDiscoveryProviderCandidate(
                    title="Video doorbell collection",
                    source_url="https://retail.example/video-doorbells",
                    snippet="Collection page without one exact model.",
                    score=0.5,
                ),
            ),
        )


class DeterministicDiscoveryAdapter:
    adapter_type = "test_competitor_discovery"

    async def execute(self, invocation: AgentInvocation) -> object:
        context = CompetitorDiscoveryInputContext.model_validate(
            invocation.task.scope["discovery_context"]
        )
        by_title = {item.title: item.candidate_id for item in context.candidates}
        output = CompetitorDiscoveryModelOutput.model_validate(
            {
                "summary": "识别两个准确型号，并排除一个集合页。",
                "proposals": [
                    {
                        "brand": "Ring",
                        "model": "Battery Doorbell Pro",
                        "variant": None,
                        "category": "smart doorbell",
                        "candidate_ids": [by_title["Ring Battery Doorbell Pro"]],
                        "comparison_dimensions": ["category_fit", "use_case"],
                        "reason": "标题明确包含门铃型号。",
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
                        "reason": "标题明确包含有线门铃型号。",
                        "confidence": 0.9,
                        "uncertainties": [],
                    },
                ],
                "excluded_candidates": [
                    {
                        "candidate_ids": [by_title["Video doorbell collection"]],
                        "reason": "没有准确型号。",
                    }
                ],
                "research_gaps": [],
                "unknowns": [],
            }
        )
        return CompetitorDiscoveryOutputValidator().validate(
            invocation.task, context, output
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'competitor-discovery.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def _approved_project(
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
            "reason": "Confirm the exact target before competitor discovery.",
        },
    )
    assert scoped.status_code == 200
    return str(project["project_id"])


def _search(client: TestClient, project_id: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/source-discovery/searches",
        json={
            "query": "eufy E340 competing smart doorbell exact models",
            "intent": "competitor_candidate",
            "provider_id": "competitor-search",
            "max_results": 5,
            "include_domains": [],
            "exclude_domains": [],
            "requested_by": "research-lead",
            "purpose": "Discover exact competitor model candidates.",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "succeeded"
    return str(response.json()["search_discovery_run_id"])


def test_discovery_artifact_requires_gate_before_scope_update(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry(
        (CompetitorSearchConnector(),)
    )

    with TestClient(application) as client:
        registry = AgentRegistry()
        registry.bind(
            ResearchAgentType.COMPETITOR_RESEARCH,
            DeterministicDiscoveryAdapter(),
        )
        application.state.competitor_discovery_registry = registry
        project_id = _approved_project(client)
        search_run_id = _search(client, project_id)
        before = client.get(f"/api/v1/projects/{project_id}/source-requirements").json()
        run = client.post(
            f"/api/v1/projects/{project_id}/agents/competitor-discovery",
            json={
                "search_discovery_run_ids": [search_run_id],
                "minimum_candidates": 2,
            },
        )
        artifact = run.json()
        after_run = client.get(f"/api/v1/projects/{project_id}/source-requirements").json()
        selected = [item["proposal_id"] for item in artifact["proposals"]]
        decided = client.post(
            f"/api/v1/projects/{project_id}/agents/competitor-discovery/artifacts/"
            f"{artifact['artifact_id']}/decision",
            json={
                "action": "confirm",
                "selected_proposal_ids": selected,
                "actor": "research-lead",
                "reason": "Both exact models are appropriate comparison candidates.",
            },
        )
        duplicate = client.post(
            f"/api/v1/projects/{project_id}/agents/competitor-discovery/artifacts/"
            f"{artifact['artifact_id']}/decision",
            json={
                "action": "confirm",
                "selected_proposal_ids": selected,
                "actor": "research-lead",
                "reason": "Duplicate decision must be rejected.",
            },
        )
        listed = client.get(
            f"/api/v1/projects/{project_id}/agents/competitor-discovery/artifacts"
        )
        evidence = client.get(f"/api/v1/projects/{project_id}/evidence").json()

    assert run.status_code == 200
    assert artifact["status"] == "completed"
    assert artifact["gate_status"] == "pending"
    assert artifact["decision"] is None
    assert artifact["coverage"]["accounted_candidate_count"] == 3
    assert len(artifact["proposals"]) == 2
    assert before["scope"]["competitors"] == []
    assert after_run["scope"]["competitors"] == []
    assert decided.status_code == 200
    result = decided.json()
    assert result["artifact"]["gate_status"] == "confirmed"
    assert {item["brand"] for item in result["source_requirements"]["scope"]["competitors"]} == {
        "Ring",
        "Google Nest",
    }
    assert result["source_requirements"]["status"] == "partial"
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "COMPETITOR_CANDIDATE_DECISION_EXISTS"
    assert listed.status_code == 200
    assert listed.json()[0]["gate_status"] == "confirmed"
    assert evidence["total"] == 0

    async def event_types() -> list[str]:
        async with application.state.database.session() as session:
            events = await ProjectRepository(session).list_events(project_id, limit=100)
        return [item.event_type for item in events]

    events = asyncio.run(event_types())
    assert "competitor_candidate_gate_decided" in events
    assert "source_requirement_scope_updated" in events


def test_discovery_rejects_cross_project_or_wrong_intent_search_runs(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry(
        (CompetitorSearchConnector(),)
    )

    with TestClient(application) as client:
        registry = AgentRegistry()
        registry.bind(ResearchAgentType.COMPETITOR_RESEARCH, DeterministicDiscoveryAdapter())
        application.state.competitor_discovery_registry = registry
        project_id = _approved_project(client)
        other_project_id = _approved_project(client, "Which other doorbells compete?")
        other_run_id = _search(client, other_project_id)
        cross_project = client.post(
            f"/api/v1/projects/{project_id}/agents/competitor-discovery",
            json={"search_discovery_run_ids": [other_run_id], "minimum_candidates": 2},
        )
        wrong_intent = client.post(
            f"/api/v1/projects/{project_id}/source-discovery/searches",
            json={
                "query": "official product sources",
                "intent": "official_product",
                "provider_id": "competitor-search",
                "max_results": 3,
                "include_domains": [],
                "exclude_domains": [],
                "requested_by": "research-lead",
                "purpose": "Official source discovery.",
            },
        ).json()["search_discovery_run_id"]
        rejected = client.post(
            f"/api/v1/projects/{project_id}/agents/competitor-discovery",
            json={"search_discovery_run_ids": [wrong_intent], "minimum_candidates": 2},
        )

    assert cross_project.status_code == 404
    assert cross_project.json()["code"] == "SEARCH_DISCOVERY_RUN_NOT_FOUND"
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "COMPETITOR_DISCOVERY_SEARCH_RUN_INVALID"
