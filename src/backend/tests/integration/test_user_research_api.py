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
from app.main import create_app
from app.sources.web_connector import WebFetchResult


class TwoPageWebConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, source_url: str) -> WebFetchResult:
        self.calls.append(source_url)
        if "reviews.example" in source_url:
            body = (
                b"<html><body><main><h1>Doorbell review</h1>"
                b"<p>I still open every package alert to understand whether "
                b"anything needs my attention.</p></main></body></html>"
            )
        else:
            body = (
                b"<html><body><main><h1>Doorbell discussion</h1>"
                b"<p>The alert says a parcel arrived, but it does not explain "
                b"whether action is urgent.</p></main></body></html>"
            )
        return WebFetchResult(
            requested_url=source_url,
            final_url=source_url,
            media_type="text/html",
            status_code=200,
            body_utf8=body,
            fetched_at=datetime(2026, 8, 8, tzinfo=UTC),
        )


class ApiUserResearchProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.evidence_ids: list[str] = []
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        first, second = self.evidence_ids
        return ProviderModelResult(
            output={
                "summary": "Users must still interpret package alerts themselves.",
                "summary_evidence_ids": [first, second],
                "event_chains": [
                    {
                        "event": "A doorbell reports a package delivery.",
                        "context": "The resident is away from home.",
                        "user_state": "The resident cannot tell whether action is urgent.",
                        "current_response": "Open the notification and inspect the video.",
                        "evidence_ids": [first, second],
                    }
                ],
                "pain_points": [
                    {
                        "pain_point_id": "manual_alert_interpretation",
                        "user_expression": "I still inspect every package alert.",
                        "trigger_event": "A package notification arrives.",
                        "context": "The package is outside while the resident is away.",
                        "severity": "medium",
                        "frequency_basis": "Observed in two independent public sources.",
                        "current_workaround": "Open the live doorbell view manually.",
                        "solution_gap": "The alert does not explain urgency.",
                        "confidence": 0.82,
                        "evidence_ids": [first, second],
                    }
                ],
                "unmet_needs": [
                    {
                        "need_id": "contextual_package_risk",
                        "statement": "Users need context about package risk.",
                        "desired_outcome": "Receive an actionable alert only when needed.",
                        "confidence": 0.78,
                        "evidence_ids": [first, second],
                    }
                ],
                "sample_biases": [],
                "research_gaps": [],
                "contradictions": [],
                "unknowns": [],
            },
            usage=ModelUsage(input_tokens=700, output_tokens=280),
            provider_request_id="api-user-research",
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
                    "model_id": "test:user-model",
                    "provider": "test",
                    "provider_model": "provider-user-model",
                    "display_name": "Test user research model",
                    "credential_env": "TEST_USER_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                }
            ]
        ),
        openai_compatible_providers_json=json.dumps(
            [{"provider_id": "test", "base_url": "https://model.invalid/v1"}]
        ),
        default_model_id="test:user-model",
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "source-processing"),
    )


def _approve_project(client: TestClient) -> str:
    created = client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": "Which unmet needs exist around eufy package alerts?",
                "category": "home security",
                "target_user": "North American smart doorbell users",
                "region": "US",
                "scenarios": ["package delivery"],
                "constraints": ["privacy first"],
                "focus_dimensions": ["user pain", "unmet needs"],
            }
        },
    )
    assert created.status_code == 201
    project = created.json()
    approved = client.post(
        f"/api/v1/projects/{project['project_id']}/decisions",
        json={
            "decision_id": project["pending_decision"]["decision_id"],
            "action": "approve",
            "reason": "The research scope is clear.",
            "actor": "research-lead",
        },
    )
    assert approved.status_code == 202
    return str(project["project_id"])


def _ingest_user_opinion_page(
    client: TestClient,
    project_id: str,
    source_url: str,
) -> str:
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": source_url,
            "display_name": "Authorized public user discussion",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "User research for package alerts",
        },
    )
    assert registered.status_code == 201
    source_asset_id = registered.json()["source_asset"]["source_asset_id"]
    processed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    assert processed.status_code == 200
    assert processed.json()["job"]["status"] == "succeeded"
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    ).json()["items"]
    assert len(fragments) == 2
    opinion_fragment = fragments[1]
    promoted = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}"
        f"/fragments/{opinion_fragment['source_fragment_id']}/evidence",
        json={
            "claim_type": "user_opinion",
            "product": "eufy doorbell",
            "region": "US",
            "user_segment": "smart doorbell users",
            "confidence": 0.85,
            "authority_score": 0.7,
            "recency_score": 0.8,
            "diversity_score": 0.9,
        },
    )
    assert promoted.status_code == 201
    evidence = promoted.json()["evidence"]
    assert evidence["source_fragment_id"] == opinion_fragment["source_fragment_id"]
    assert evidence["original_excerpt"] == opinion_fragment["original_excerpt"]
    assert evidence["status"] == "partially_verified"
    return str(evidence["evidence_id"])


def test_web_sources_flow_through_evidence_and_user_research_api(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_USER_MODEL_KEY", "test-secret")
    application = create_app(_settings(tmp_path))
    connector = TwoPageWebConnector()
    provider = ApiUserResearchProvider()
    application.state.web_connector = connector
    application.state.model_provider_registry.register(provider, replace=True)

    with TestClient(application) as client:
        project_id = _approve_project(client)
        provider.evidence_ids = [
            _ingest_user_opinion_page(
                client, project_id, "https://reviews.example/eufy-package-alerts"
            ),
            _ingest_user_opinion_page(
                client, project_id, "https://community.example/doorbell-packages"
            ),
        ]

        research = client.post(
            f"/api/v1/projects/{project_id}/agents/user-research"
        )
        artifacts = client.get(
            f"/api/v1/projects/{project_id}/agents/user-research/artifacts"
        )
        agent_runs = client.get(f"/api/v1/projects/{project_id}/agents")

    assert research.status_code == 200
    artifact = research.json()
    assert artifact["status"] == "completed"
    assert set(artifact["evidence_ids"]) == set(provider.evidence_ids)
    assert artifact["payload"]["evidence_coverage"] == {
        "available_evidence_count": 2,
        "included_evidence_count": 2,
        "cited_evidence_count": 2,
        "independent_domain_count": 2,
        "user_opinion_evidence_count": 2,
        "context_hash": artifact["payload"]["evidence_coverage"]["context_hash"],
    }
    assert artifacts.status_code == 200
    assert [item["artifact_id"] for item in artifacts.json()] == [
        artifact["artifact_id"]
    ]
    user_run = next(
        run for run in agent_runs.json() if run["agent_type"] == "user_research"
    )
    assert user_run["status"] == "completed"
    assert user_run["model_id"] == "test:user-model"
    assert user_run["input_tokens"] == 700
    assert len(connector.calls) == 2
    assert len(provider.requests) == 1
    assert "test-secret" not in provider.requests[0].messages[1].content
