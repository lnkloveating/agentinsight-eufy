import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.competitor import UserReviewEvidenceContextBuilder
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


class ReviewPageConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, source_url: str) -> WebFetchResult:
        self.calls.append(source_url)
        if "reviews-a" in source_url:
            review = "Package alerts are often delayed after delivery."
        else:
            review = "The notification arrived late after my parcel was left outside."
        return WebFetchResult(
            requested_url=source_url,
            final_url=source_url,
            media_type="text/html",
            status_code=200,
            body_utf8=(
                f"<html><body><main><p>Verified owner review: {review}</p>"
                "</main></body></html>"
            ).encode(),
            fetched_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        )


class UserReviewProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.evidence_ids: list[str] = []
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        return ProviderModelResult(
            output={
                "summary": "两个独立评论来源都描述了包裹通知延迟。",
                "summary_evidence_ids": self.evidence_ids,
                "review_themes": [
                    {
                        "theme_id": "theme_delayed_package_notification",
                        "scope_label": "Target Doorbell",
                        "theme": "包裹通知延迟",
                        "sentiment": "negative",
                        "user_expression": "用户表示包裹送达后通知较晚。",
                        "event_context": "包裹已经留在门外之后",
                        "user_impact": "用户无法及时处理门外包裹。",
                        "user_segment": "doorbell owner",
                        "region": "US",
                        "confidence": 0.86,
                        "evidence_ids": self.evidence_ids,
                    }
                ],
                "contradictions": [],
                "sample_limitations": [
                    {
                        "scope_label": "Target Doorbell",
                        "description": "当前仅包含两个公开评论来源。",
                        "impact": "不能推断总体发生比例。",
                        "evidence_ids": self.evidence_ids,
                    }
                ],
                "research_gaps": [],
                "unknowns": ["总体发生比例未知"],
            },
            usage=ModelUsage(input_tokens=780, output_tokens=340),
            provider_request_id="competitor-user-review-provider-request",
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
                    "model_id": "test:review-model",
                    "provider": "test",
                    "provider_model": "provider-review-model",
                    "display_name": "Competitor review test model",
                    "credential_env": "TEST_REVIEW_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                }
            ]
        ),
        openai_compatible_providers_json=json.dumps(
            [{"provider_id": "test", "base_url": "https://model.invalid/v1"}]
        ),
        default_model_id="test:review-model",
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "source-processing"),
    )


def _approve_project(client: TestClient) -> str:
    created = client.post(
        "/api/v1/projects",
        json={
            "brief": home_safety_brief_payload(
                "What recurring opinions affect AI-native home-safety ecosystems?"
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
            "reason": "The product and authorized review scope are explicit.",
            "actor": "research-lead",
        },
    )
    assert approved.status_code == 202
    return str(project["project_id"])


def _ingest_review_page(
    client: TestClient,
    project_id: str,
    source_url: str,
    *,
    confirm_route: bool = True,
) -> str:
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": source_url,
            "display_name": "Authorized owner review",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "User review and customer opinion research",
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
    if confirm_route:
        decision = {
            "action": "confirm",
            "selections": [{"route": "user_review", "claim_types": ["user_opinion"]}],
            "actor": "research-lead",
            "reason": "The excerpt is an authorized first-person owner review.",
        }
    else:
        decision = {
            "action": "reject",
            "selections": [],
            "actor": "research-lead",
            "reason": "Reject this route to verify downstream isolation.",
        }
    routed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/decision",
        json=decision,
    )
    assert routed.status_code == 200
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    ).json()["items"]
    assert len(fragments) == 1
    promoted = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}"
        f"/fragments/{fragments[0]['source_fragment_id']}/evidence",
        json={
            "claim_type": "user_opinion",
            "product": "Target Doorbell",
            "region": "US",
            "user_segment": "doorbell owner",
            "confidence": 0.85,
            "authority_score": 0.7,
            "recency_score": 0.8,
            "diversity_score": 0.8,
        },
    )
    assert promoted.status_code == 201
    return str(promoted.json()["evidence"]["evidence_id"])


def test_rejected_route_is_excluded_from_user_review_context(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    application.state.web_connector = ReviewPageConnector()
    with TestClient(application) as client:
        project_id = _approve_project(client)
        evidence_id = _ingest_review_page(
            client,
            project_id,
            "https://reviews-a.example/target-doorbell",
            confirm_route=False,
        )
        context = asyncio.run(
            UserReviewEvidenceContextBuilder(
                application.state.database,
                max_items=20,
                max_excerpt_chars=3_000,
                max_total_chars=20_000,
            ).build(project_id)
        )

    assert evidence_id
    assert context.items == []
    assert context.available_evidence_count == 0


def test_two_authorized_review_sources_flow_to_bound_a2a_specialist(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_REVIEW_MODEL_KEY", "test-secret")
    application = create_app(_settings(tmp_path))
    connector = ReviewPageConnector()
    provider = UserReviewProvider()
    application.state.web_connector = connector
    application.state.model_provider_registry.register(provider, replace=True)

    with TestClient(application) as client:
        project_id = _approve_project(client)
        provider.evidence_ids = [
            _ingest_review_page(
                client, project_id, "https://reviews-a.example/target-doorbell"
            ),
            _ingest_review_page(
                client, project_id, "https://reviews-b.example/target-doorbell"
            ),
        ]

        async def run_review_research() -> tuple[object, object, object]:
            evidence_context = await UserReviewEvidenceContextBuilder(
                application.state.database,
                max_items=20,
                max_excerpt_chars=3_000,
                max_total_chars=20_000,
            ).build(project_id)
            task = ResearchTask(
                task_id="task_competitor_review_e2e",
                project_id=project_id,
                agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
                goal="Create evidence-backed competitor user-review intelligence.",
                scope={"target_product": "Target Doorbell"},
                evidence_rules=EvidenceRules(
                    citation_required=True, minimum_independent_domains=2
                ),
                budget=ResearchBudget(max_pages=20, deadline_seconds=120),
            )
            artifact = await AgentRuntimeGateway(
                application.state.database,
                application.state.agent_registry,
                application.state.event_broker,
                "trace_review_e2e",
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

        artifact, raw_tasks, raw_calls = asyncio.run(run_review_research())

    tasks = list(raw_tasks)
    calls = list(raw_calls)
    review_task = next(item for item in tasks if item.specialist_type == "user_review")
    official_task = next(item for item in tasks if item.specialist_type == "official_product")
    price_task = next(item for item in tasks if item.specialist_type == "price_channel")
    assert artifact.status == "partial"
    assert review_task.status == "completed"
    assert official_task.status == "blocked"
    assert price_task.status == "blocked"
    assert all(item.adapter_type != "unbound" for item in tasks)
    assert all(item.error_code is None for item in tasks)
    assert not any("specialist is not bound" in item for item in artifact.unknowns)
    payload = review_task.output_json["structured_payload"]
    assert payload["schema_name"] == "competitor_user_review_intelligence"
    assert payload["review_themes"][0]["recurrence_status"] == (
        "repeated_across_sources"
    )
    assert review_task.output_json["evidence_ids"] == sorted(provider.evidence_ids)
    assert len(provider.requests) == 1
    assert all(
        evidence_id in provider.requests[0].messages[1].content
        for evidence_id in provider.evidence_ids
    )
    assert "test-secret" not in provider.requests[0].messages[1].content
    assert len(calls) == 1
    assert calls[0].prompt_key == "agent:competitor_user_review"
