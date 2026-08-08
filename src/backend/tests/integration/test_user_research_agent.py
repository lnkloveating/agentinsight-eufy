import json
from datetime import UTC, datetime

import pytest

from app.agents.user_research import UserResearchModelAgentAdapter
from app.agents.user_research.context import UserResearchEvidenceContextBuilder
from app.agents.user_research.prompt import register_user_research_prompt
from app.application.events import ProjectEventBroker
from app.application.evidence import EvidenceService
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
from app.application.research import UserResearchService
from app.application.runtime import (
    AgentRegistry,
    AgentRuntimeGateway,
    ArtifactStore,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import EvidenceClaimType, EvidenceIngest, EvidenceStatus
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import ResearchAgentType


def test_user_research_runtime_error_is_exposed_as_safe_api_error() -> None:
    mapped = UserResearchService._public_runtime_error(
        RuntimeGatewayError(
            RuntimeErrorCode.TIMEOUT,
            "raw provider detail must stay private",
            agent_run_id="run_timeout",
            retryable=True,
        )
    )

    assert mapped.status_code == 504
    assert mapped.code == "USER_RESEARCH_TIMEOUT"
    assert mapped.details == {
        "agent_run_id": "run_timeout",
        "runtime_error_code": RuntimeErrorCode.TIMEOUT,
        "retryable": True,
    }
    assert "raw provider detail" not in mapped.message


class UserResearchProvider:
    provider_id = "test"

    def __init__(self, evidence_ids: list[str]) -> None:
        self.evidence_ids = evidence_ids
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        first, second = self.evidence_ids
        return ProviderModelResult(
            output={
                "summary": "用户仍需要自行解释门铃通知。",
                "summary_evidence_ids": [first, second],
                "event_chains": [
                    {
                        "event": "包裹送达后门铃发出通知。",
                        "context": "用户不在家。",
                        "user_state": "用户无法直接判断是否需要立即处理。",
                        "current_response": "打开通知并查看画面。",
                        "evidence_ids": [first, second],
                    }
                ],
                "pain_points": [
                    {
                        "pain_point_id": "manual_alert_interpretation",
                        "user_expression": "每次通知仍然需要我自己打开确认。",
                        "trigger_event": "收到门铃包裹通知。",
                        "context": "用户离家且包裹留在门外。",
                        "severity": "medium",
                        "frequency_basis": "来自两个独立公开评论来源。",
                        "current_workaround": "手动打开直播画面。",
                        "solution_gap": "通知没有结合上下文说明是否需要立即行动。",
                        "confidence": 0.82,
                        "evidence_ids": [first, second],
                    }
                ],
                "unmet_needs": [
                    {
                        "need_id": "contextual_risk",
                        "statement": "用户需要理解包裹当前风险，而不只是知道已送达。",
                        "desired_outcome": "只在确实需要处理时收到可行动建议。",
                        "confidence": 0.78,
                        "evidence_ids": [first, second],
                    }
                ],
                "sample_biases": [],
                "research_gaps": [],
                "contradictions": [],
                "unknowns": [],
            },
            usage=ModelUsage(input_tokens=900, output_tokens=350),
            provider_request_id="provider-user-research",
        )


def _brief() -> ResearchBrief:
    return ResearchBrief(
        question="调研 eufy 家庭安防未来产品机会",
        category="家庭安防",
        target_user="北美家庭安防用户",
        region="US",
        scenarios=["门前包裹"],
    )


def _evidence(url: str, excerpt: str) -> EvidenceIngest:
    return EvidenceIngest(
        source_url=url,
        source_type="webpage",
        title="Public user review",
        original_excerpt=excerpt,
        claim_type=EvidenceClaimType.USER_OPINION,
        collected_at=datetime.now(UTC),
        status=EvidenceStatus.VERIFIED,
        confidence=0.9,
        authority_score=0.7,
        recency_score=0.8,
        diversity_score=0.9,
    )


@pytest.mark.asyncio
async def test_user_research_service_runs_real_runtime_contract_and_persists_versions() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    broker = ProjectEventBroker()
    try:
        now = datetime.now(UTC)
        async with database.session() as session:
            session.add(
                ProjectModel(
                    project_id="proj_user_agent",
                    status=ProjectStatus.RESEARCHING,
                    current_stage="parallel_research",
                    progress=20,
                    brief_json=_brief().model_dump(mode="json"),
                    model_selection_json={
                        "default_model_id": "test:user-model",
                        "agent_overrides": {},
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            evidence_service = EvidenceService(
                EvidenceRepository(session),
                ProjectRepository(session),
                "trace_user_agent",
                broker,
            )
            first = await evidence_service.ingest(
                "proj_user_agent",
                _evidence(
                    "https://reviews.example/eufy",
                    "I still open every package alert to decide what happened.",
                ),
            )
            second = await evidence_service.ingest(
                "proj_user_agent",
                _evidence(
                    "https://community.example/doorbell",
                    "The alert tells me a package arrived but not whether action is urgent.",
                ),
            )

        provider = UserResearchProvider(
            [first.evidence.evidence_id, second.evidence.evidence_id]
        )
        providers = ModelProviderRegistry()
        providers.register(provider)
        catalog = ModelCatalog.from_json(
            json.dumps(
                [
                    {
                        "model_id": "test:user-model",
                        "provider": "test",
                        "provider_model": "provider-user-model",
                        "display_name": "User research model",
                        "credential_env": "TEST_USER_MODEL_KEY",
                        "capabilities": ["text", "structured_output"],
                    }
                ]
            ),
            default_model_id="test:user-model",
        )
        model_gateway = ModelGateway(
            database,
            catalog,
            EnvironmentCredentialResolver(
                {"TEST_USER_MODEL_KEY": "test-user-model-secret"}
            ),
            providers,
            max_retries=0,
        )
        prompts = PromptRegistry()
        register_user_research_prompt(prompts)
        registry = AgentRegistry()
        registry.bind(
            ResearchAgentType.USER_RESEARCH,
            UserResearchModelAgentAdapter(
                model_gateway,
                prompts,
                ProjectModelSelectionResolver(database),
            ),
        )
        service = UserResearchService(
            database,
            AgentRuntimeGateway(
                database, registry, broker, "trace_user_agent_runtime"
            ),
            UserResearchEvidenceContextBuilder(
                database,
                max_items=10,
                max_excerpt_chars=2_000,
                max_total_chars=20_000,
            ),
        )

        first_artifact = await service.run("proj_user_agent")
        second_artifact = await service.run("proj_user_agent")
        versions = await service.list_artifacts("proj_user_agent")

        assert first_artifact.status == "completed"
        assert second_artifact.status == "completed"
        assert first_artifact.artifact_id != second_artifact.artifact_id
        assert len(versions) == 2
        assert versions[0].payload.pain_points[0].pain_point_id == (
            "manual_alert_interpretation"
        )
        assert len(provider.requests) == 2
        assert "evidence_context=" in provider.requests[0].messages[1].content
        assert "test-user-model-secret" not in provider.requests[0].messages[1].content

        stored = await ArtifactStore(database).list_versions(
            "proj_user_agent", "task_user_research"
        )
        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs("proj_user_agent")
            calls = await ModelCallRepository(session).list_for_run(runs[-1].agent_run_id)
        assert [item.version for item in stored] == [1, 2]
        assert runs[-1].status == "completed"
        assert runs[-1].model_id == "test:user-model"
        assert runs[-1].prompt_key == "agent:user_research"
        assert runs[-1].input_tokens == 900
        assert len(calls) == 1
        assert calls[0].provider_request_id == "provider-user-research"
    finally:
        await database.dispose()
