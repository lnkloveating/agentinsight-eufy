import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.competitor import OfficialProductEvidenceContextBuilder
from app.application.model_gateway import (
    ModelUsage,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.application.runtime import AgentRuntimeGateway
from app.core.config import Settings
from app.infrastructure.database.a2a_repository import A2ATaskRepository
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.schemas.project import ResearchBrief
from app.sources.web_connector import WebFetchResult
from app.workflows.contracts import (
    AgentContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)


class OfficialPageConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, source_url: str) -> WebFetchResult:
        self.calls.append(source_url)
        return WebFetchResult(
            requested_url=source_url,
            final_url="https://vendor.example/products/target-doorbell",
            media_type="text/html",
            status_code=200,
            body_utf8=(
                b"<html><body><main><h1>Target Doorbell MODEL-1</h1>"
                b"<p>Local package detection is supported in the US region.</p>"
                b"</main></body></html>"
            ),
            fetched_at=datetime(2026, 8, 8, tzinfo=UTC),
        )


class OfficialProductProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.evidence_ids: list[str] = []
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        identity, capability = self.evidence_ids
        return ProviderModelResult(
            output={
                "summary": "官方页面声明该型号支持在美国地区进行本地包裹检测。",
                "summary_evidence_ids": [identity, capability],
                "products": [
                    {
                        "scope_label": "Target Doorbell",
                        "official_name": "Target Doorbell",
                        "model_numbers": ["MODEL-1"],
                        "evidence_ids": [identity],
                        "facts": [
                            {
                                "fact_id": "fact_local_package_detection",
                                "fact_type": "capability",
                                "field_name": "包裹检测",
                                "value": "支持本地处理",
                                "qualifiers": {"region": "US"},
                                "confidence": 0.9,
                                "evidence_ids": [capability],
                            }
                        ],
                        "unknown_fields": ["最低固件版本"],
                    }
                ],
                "contradictions": [],
                "research_gaps": [
                    {
                        "scope_label": "Target Doorbell",
                        "question": "最低固件版本是什么？",
                        "reason": "当前官方页面片段没有说明。",
                        "severity": "medium",
                        "recommended_source_types": ["official_support_document"],
                    }
                ],
                "unknowns": ["最低固件版本未知"],
            },
            usage=ModelUsage(input_tokens=850, output_tokens=360),
            provider_request_id="official-product-provider-request",
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
                    "model_id": "test:official-model",
                    "provider": "test",
                    "provider_model": "provider-official-model",
                    "display_name": "Official product test model",
                    "credential_env": "TEST_OFFICIAL_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                }
            ]
        ),
        openai_compatible_providers_json=json.dumps(
            [{"provider_id": "test", "base_url": "https://model.invalid/v1"}]
        ),
        default_model_id="test:official-model",
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "source-processing"),
    )


def _approve_project(client: TestClient) -> str:
    created = client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": "Which future opportunities exist in home security?",
                "category": "home security",
                "target_user": "North American households",
                "region": "US",
                "scenarios": ["front door package"],
                "constraints": ["privacy first"],
                "focus_dimensions": ["official capabilities"],
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
            "reason": "The scope and authorized source are clear.",
            "actor": "research-lead",
        },
    )
    assert approved.status_code == 202
    return str(project["project_id"])


def _ingest_official_page(client: TestClient, project_id: str) -> list[str]:
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "https://vendor.example/products/target-doorbell",
            "display_name": "Authorized official product page",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "Official product capability research",
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

    evidence_ids: list[str] = []
    for fragment in fragments:
        promoted = client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}"
            f"/fragments/{fragment['source_fragment_id']}/evidence",
            json={
                "claim_type": "vendor_claim",
                "product": "Target Doorbell",
                "region": "US",
                "confidence": 0.9,
                "authority_score": 0.9,
                "recency_score": 0.8,
                "diversity_score": 0.5,
            },
        )
        assert promoted.status_code == 201
        evidence = promoted.json()["evidence"]
        assert evidence["source_fragment_id"] == fragment["source_fragment_id"]
        assert evidence["original_excerpt"] == fragment["original_excerpt"]
        evidence_ids.append(str(evidence["evidence_id"]))
    return evidence_ids


def test_authorized_webpage_flows_to_real_official_product_specialist_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_OFFICIAL_MODEL_KEY", "test-secret")
    application = create_app(_settings(tmp_path))
    connector = OfficialPageConnector()
    provider = OfficialProductProvider()
    application.state.web_connector = connector
    application.state.model_provider_registry.register(provider, replace=True)

    with TestClient(application) as client:
        project_id = _approve_project(client)
        provider.evidence_ids = _ingest_official_page(client, project_id)

        async def run_official_research() -> tuple[object, object, object]:
            context_builder = OfficialProductEvidenceContextBuilder(
                application.state.database,
                max_items=20,
                max_excerpt_chars=3_000,
                max_total_chars=20_000,
            )
            evidence_context = await context_builder.build(project_id)
            task = ResearchTask(
                task_id="task_competitor_official_e2e",
                project_id=project_id,
                agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
                goal="Create evidence-backed official product intelligence.",
                scope={"target_product": "Target Doorbell"},
                evidence_rules=EvidenceRules(
                    citation_required=True,
                    minimum_independent_domains=2,
                ),
                budget=ResearchBudget(max_pages=20, deadline_seconds=120),
            )
            runtime = AgentRuntimeGateway(
                application.state.database,
                application.state.agent_registry,
                application.state.event_broker,
                "trace_official_e2e",
            )
            artifact = await runtime.execute(
                task,
                AgentContext(
                    project_id=project_id,
                    brief=_research_brief(),
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

        artifact, raw_tasks, raw_model_calls = asyncio.run(run_official_research())

    a2a_tasks = list(raw_tasks)
    model_calls = list(raw_model_calls)
    official_task = next(
        task for task in a2a_tasks if task.specialist_type == "official_product"
    )
    assert artifact.status == "partial"  # The other two specialists are intentionally unbound.
    assert official_task.status == "completed"
    assert official_task.output_json["evidence_ids"] == sorted(provider.evidence_ids)
    assert official_task.output_json["structured_payload"]["products"][0][
        "scope_label"
    ] == "Target Doorbell"
    assert connector.calls == ["https://vendor.example/products/target-doorbell"]
    assert len(provider.requests) == 1
    assert all(
        evidence_id in provider.requests[0].messages[1].content
        for evidence_id in provider.evidence_ids
    )
    assert "test-secret" not in provider.requests[0].messages[1].content
    assert len(model_calls) == 1
    assert model_calls[0].prompt_key == "agent:competitor_official_product"


def _research_brief() -> ResearchBrief:
    return ResearchBrief(
        question="Which future opportunities exist in home security?",
        category="home security",
        target_user="North American households",
        region="US",
        scenarios=["front door package"],
    )
