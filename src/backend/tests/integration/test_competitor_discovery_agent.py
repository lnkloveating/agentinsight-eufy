import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.agents.competitor.discovery_adapter import CompetitorDiscoveryModelAgentAdapter
from app.agents.competitor.discovery_prompt import register_competitor_discovery_prompt
from app.application.events import ProjectEventBroker
from app.application.model_gateway import (
    EnvironmentCredentialResolver,
    ModelCatalog,
    ModelGateway,
    ModelProviderRegistry,
    ModelUsage,
    ProjectModelSelectionResolver,
    PromptRegistry,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.application.runtime import AgentRegistry, AgentRuntimeGateway, ArtifactStore
from app.infrastructure.database import Database
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import AgentContext, EvidenceRules, ResearchAgentType, ResearchTask
from tests.research_brief import home_safety_brief


class CompetitorDiscoveryProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        return ProviderModelResult(
            output={
                "summary": "搜索候选中有一个准确竞品型号。",
                "proposals": [
                    {
                        "brand": "Ring",
                        "model": "Battery Doorbell Pro",
                        "variant": None,
                        "category": "smart doorbell",
                        "candidate_ids": ["candidate_ring"],
                        "comparison_dimensions": ["category_fit", "use_case"],
                        "reason": "标题明确包含品牌和型号。",
                        "confidence": 0.91,
                        "uncertainties": [],
                    }
                ],
                "excluded_candidates": [
                    {
                        "candidate_ids": ["candidate_collection"],
                        "reason": "集合页没有准确型号。",
                    }
                ],
                "research_gaps": [],
                "unknowns": [],
            },
            usage=ModelUsage(input_tokens=220, output_tokens=90),
            provider_request_id="provider-competitor-discovery",
        )


def _brief() -> ResearchBrief:
    return home_safety_brief()


@pytest.mark.asyncio
async def test_competitor_discovery_adapter_uses_model_gateway_and_persists_audit(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'discovery-agent.db'}")
    await database.create_schema()
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            ProjectModel(
                project_id="proj_competitor_discovery",
                status=ProjectStatus.RESEARCHING,
                current_stage="competitor_discovery",
                progress=20,
                brief_json=_brief().model_dump(mode="json"),
                model_selection_json={
                    "default_model_id": "test:default",
                    "agent_overrides": {
                        "competitor_research": "test:competitor-discovery"
                    },
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    provider = CompetitorDiscoveryProvider()
    providers = ModelProviderRegistry()
    providers.register(provider)
    catalog = ModelCatalog.from_json(
        json.dumps(
            [
                {
                    "model_id": "test:default",
                    "provider": "test",
                    "provider_model": "provider-default",
                    "display_name": "Default model",
                    "credential_env": "TEST_DISCOVERY_KEY",
                    "capabilities": ["text", "structured_output"],
                },
                {
                    "model_id": "test:competitor-discovery",
                    "provider": "test",
                    "provider_model": "provider-discovery",
                    "display_name": "Discovery model",
                    "credential_env": "TEST_DISCOVERY_KEY",
                    "capabilities": ["text", "structured_output"],
                },
            ]
        )
    )
    gateway = ModelGateway(
        database,
        catalog,
        EnvironmentCredentialResolver({"TEST_DISCOVERY_KEY": "test-only-secret"}),
        providers,
        max_retries=0,
    )
    prompts = PromptRegistry()
    register_competitor_discovery_prompt(prompts)
    registry = AgentRegistry()
    registry.bind(
        ResearchAgentType.COMPETITOR_RESEARCH,
        CompetitorDiscoveryModelAgentAdapter(
            gateway,
            prompts,
            ProjectModelSelectionResolver(database),
        ),
    )
    runtime = AgentRuntimeGateway(
        database,
        registry,
        ProjectEventBroker(),
        "trace_competitor_discovery",
    )
    task = ResearchTask(
        task_id="task_competitor_discovery",
        project_id="proj_competitor_discovery",
        agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
        goal="Identify exact competitor candidates for human review.",
        evidence_rules=EvidenceRules(citation_required=False),
        scope={
            "discovery_context": {
                "target_products": [{"brand": "eufy", "model": "E340"}],
                "search_discovery_run_ids": ["search_test"],
                "candidates": [
                    {
                        "candidate_id": "candidate_ring",
                        "search_discovery_run_id": "search_test",
                        "title": "Ring Battery Doorbell Pro",
                        "source_url": "https://ring.example/battery-doorbell-pro",
                        "source_domain": "ring.example",
                        "snippet": "Ring Battery Doorbell Pro candidate.",
                        "search_score": 0.9,
                    },
                    {
                        "candidate_id": "candidate_collection",
                        "search_discovery_run_id": "search_test",
                        "title": "Video doorbell collection",
                        "source_url": "https://retail.example/video-doorbells",
                        "source_domain": "retail.example",
                        "snippet": "Collection page without an exact model.",
                        "search_score": 0.5,
                    },
                ],
                "minimum_candidates": 1,
                "context_hash": "a" * 64,
            }
        },
    )
    context = AgentContext(
        project_id="proj_competitor_discovery",
        brief=_brief(),
        iteration=0,
    )

    try:
        artifact = await runtime.execute(task, context)

        assert artifact.status == "completed"
        assert artifact.evidence_ids == []
        assert artifact.payload["proposals"][0]["model"] == "Battery Doorbell Pro"
        assert provider.requests[0].provider_model == "provider-discovery"
        assert provider.requests[0].credential == "test-only-secret"
        assert "candidate_only" in provider.requests[0].messages[0].content
        assert "candidate_ring" in provider.requests[0].messages[1].content
        stored = await ArtifactStore(database).list_versions(
            "proj_competitor_discovery", "task_competitor_discovery"
        )
        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs(
                "proj_competitor_discovery"
            )
            calls = await ModelCallRepository(session).list_for_run(runs[0].agent_run_id)
        assert len(stored) == 1
        assert stored[0].artifact.evidence_ids == []
        assert runs[0].model_id == "test:competitor-discovery"
        assert runs[0].prompt_key == "agent:competitor_discovery"
        assert runs[0].input_tokens == 220
        assert len(calls) == 1
        assert calls[0].status == "completed"
    finally:
        await database.dispose()
