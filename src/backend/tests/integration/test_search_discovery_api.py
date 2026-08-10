import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.infrastructure.database.models import (
    EvidenceModel,
    ModelCallModel,
    SearchDiscoveryRunModel,
    SourceAssetModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.sources.search_discovery import (
    SearchDiscoveryProviderCandidate,
    SearchDiscoveryProviderError,
    SearchDiscoveryProviderRequest,
    SearchDiscoveryProviderResponse,
    SearchDiscoveryRegistry,
)
from tests.research_brief import home_safety_brief_payload


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'search-discovery.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def _create_project(
    client: TestClient,
    question: str = "How should the eufy home-safety ecosystem evolve?",
) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "brief": home_safety_brief_payload(question)
        },
    )
    assert response.status_code == 201
    return str(response.json()["project_id"])


@dataclass
class SuccessfulConnector:
    provider_id: str = "test-search"
    available: bool = True
    unavailable_reason: str | None = None
    received: SearchDiscoveryProviderRequest | None = None

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse:
        self.received = request
        return SearchDiscoveryProviderResponse(
            provider_request_id="provider-request-1",
            candidates=(
                SearchDiscoveryProviderCandidate(
                    title="  eufy E340 official page  ",
                    source_url="https://www.eufy.com/products/e340?utm_source=search",
                    snippet=" Candidate summary; it is not evidence. ",
                    score=0.95,
                ),
                SearchDiscoveryProviderCandidate(
                    title="duplicate",
                    source_url="https://www.eufy.com/products/e340",
                    snippet="duplicate",
                    score=0.9,
                ),
                SearchDiscoveryProviderCandidate(
                    title="excluded support page",
                    source_url="https://support.eufy.com/article/e340",
                    snippet="excluded",
                    score=0.8,
                ),
                SearchDiscoveryProviderCandidate(
                    title="private address",
                    source_url="http://127.0.0.1/private",
                    snippet="unsafe",
                    score=0.7,
                ),
                SearchDiscoveryProviderCandidate(
                    title="outside allowlist",
                    source_url="https://example.com/e340",
                    snippet="outside",
                    score=0.6,
                ),
            ),
        )


@dataclass
class UnavailableConnector:
    provider_id: str = "missing-key"
    available: bool = False
    unavailable_reason: str | None = "SEARCH_CREDENTIAL_MISSING"

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse:
        del request
        raise AssertionError("unavailable connector must not be called")


@dataclass
class FailingConnector:
    provider_id: str = "rate-limited"
    available: bool = True
    unavailable_reason: str | None = None

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse:
        del request
        raise SearchDiscoveryProviderError(
            "SEARCH_RATE_LIMITED",
            "Search quota reached.",
            blocked=False,
            retryable=True,
        )


def _request(provider_id: str) -> dict[str, object]:
    return {
        "query": "eufy E340 official product page",
        "intent": "official_product",
        "provider_id": provider_id,
        "max_results": 5,
        "include_domains": ["eufy.com"],
        "exclude_domains": ["support.eufy.com"],
        "requested_by": "research-lead",
        "purpose": "Discover candidate URLs before authorization and onboarding.",
    }


def test_search_candidates_are_sanitized_persisted_and_never_promoted_to_evidence(
    tmp_path: Path,
) -> None:
    connector = SuccessfulConnector()
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry((connector,))

    with TestClient(application) as client:
        project_id = _create_project(client)
        other_project_id = _create_project(client, "How should another product evolve?")
        created = client.post(
            f"/api/v1/projects/{project_id}/source-discovery/searches",
            json=_request(connector.provider_id),
        )
        body = created.json()
        run_id = body["search_discovery_run_id"]
        fetched = client.get(
            f"/api/v1/projects/{project_id}/source-discovery/searches/{run_id}"
        )
        listed = client.get(
            f"/api/v1/projects/{project_id}/source-discovery/searches?limit=10"
        )
        cross_project = client.get(
            f"/api/v1/projects/{other_project_id}/source-discovery/searches/{run_id}"
        )
        source_assets = client.get(f"/api/v1/projects/{project_id}/sources")

    assert created.status_code == 201
    assert body["status"] == "succeeded"
    assert body["provider_request_id"] == "provider-request-1"
    assert body["result_count"] == 1
    assert body["error_code"] is None
    assert body["retryable"] is False
    candidate = body["candidates"][0]
    assert candidate["title"] == "eufy E340 official page"
    assert candidate["source_url"] == "https://www.eufy.com/products/e340"
    assert candidate["source_domain"] == "www.eufy.com"
    assert candidate["evidence_status"] == "candidate_only"
    assert fetched.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert cross_project.status_code == 404
    assert source_assets.json()["total"] == 0
    assert connector.received is not None
    assert connector.received.include_domains == ("eufy.com",)

    async def audit() -> tuple[int, int, int, int, list[str]]:
        async with application.state.database.session() as session:
            run_count = int(
                await session.scalar(select(func.count()).select_from(SearchDiscoveryRunModel))
                or 0
            )
            source_count = int(
                await session.scalar(select(func.count()).select_from(SourceAssetModel)) or 0
            )
            evidence_count = int(
                await session.scalar(select(func.count()).select_from(EvidenceModel)) or 0
            )
            model_call_count = int(
                await session.scalar(select(func.count()).select_from(ModelCallModel)) or 0
            )
            events = await ProjectRepository(session).list_events(project_id, limit=100)
        return (
            run_count,
            source_count,
            evidence_count,
            model_call_count,
            [event.event_type for event in events],
        )

    run_count, source_count, evidence_count, model_call_count, event_types = asyncio.run(audit())
    assert (run_count, source_count, evidence_count, model_call_count) == (1, 0, 0, 0)
    assert "search_discovery_running" in event_types
    assert "search_discovery_succeeded" in event_types


def test_missing_credential_and_provider_failure_are_auditable_results(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry(
        (UnavailableConnector(), FailingConnector())
    )

    with TestClient(application) as client:
        project_id = _create_project(client)
        blocked = client.post(
            f"/api/v1/projects/{project_id}/source-discovery/searches",
            json=_request("missing-key"),
        )
        failed = client.post(
            f"/api/v1/projects/{project_id}/source-discovery/searches",
            json=_request("rate-limited"),
        )
        unknown = client.post(
            f"/api/v1/projects/{project_id}/source-discovery/searches",
            json=_request("unknown-provider"),
        )
        listed = client.get(f"/api/v1/projects/{project_id}/source-discovery/searches")

    assert blocked.status_code == 201
    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["error_code"] == "SEARCH_CREDENTIAL_MISSING"
    assert blocked.json()["candidates"] == []
    assert failed.status_code == 201
    assert failed.json()["status"] == "failed"
    assert failed.json()["error_code"] == "SEARCH_RATE_LIMITED"
    assert failed.json()["retryable"] is True
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "SEARCH_PROVIDER_NOT_FOUND"
    assert listed.json()["total"] == 2
