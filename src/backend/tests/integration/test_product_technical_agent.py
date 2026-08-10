import json
from datetime import UTC, datetime

import pytest

from app.agents.product_technical import (
    ProductTechnicalEvidenceContextBuilder,
    ProductTechnicalModelAgentAdapter,
    register_product_technical_prompt,
)
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
from app.application.research import ProductTechnicalService
from app.application.runtime import AgentRegistry, AgentRuntimeGateway, ArtifactStore
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import EvidenceClaimType, EvidenceIngest, EvidenceStatus
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)


class StaticArtifactAdapter:
    adapter_type = "static_test_upstream"

    def __init__(self, artifact: ResearchArtifact) -> None:
        self.artifact = artifact

    async def execute(self, invocation) -> object:  # type: ignore[no-untyped-def]
        return self.artifact.model_copy(
            update={
                "task_id": invocation.task.task_id,
                "artifact_type": invocation.task.agent_type.value,
            }
        )


class ProductOpportunityProvider:
    provider_id = "product-test"

    def __init__(self, user_evidence_id: str, competitor_evidence_id: str) -> None:
        self.user_evidence_id = user_evidence_id
        self.competitor_evidence_id = competitor_evidence_id
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        candidates = [self._candidate(index) for index in range(1, 4)]
        return ProviderModelResult(
            output={
                "summary": "动态设备品类存在三个有证据支持的事件理解机会。",
                "summary_evidence_ids": [
                    self.user_evidence_id,
                    self.competitor_evidence_id,
                ],
                "candidates": candidates,
                "portfolio_gaps": [],
                "unknowns": [],
            },
            usage=ModelUsage(input_tokens=1_200, output_tokens=800),
            provider_request_id="provider-product-technical",
        )

    def _candidate(self, index: int) -> dict[str, object]:
        return {
            "candidate_id": f"dynamic_future_{index}",
            "name": f"动态未来机会 {index}",
            "target_user": {"persona_ids": ["dynamic_user"], "description": "动态设备用户"},
            "problem": {
                "pain_ids": ["manual_interpretation"],
                "description": "用户仍需手动解释设备事件。",
            },
            "event_understanding": {
                "base_event": {"type": f"dynamic_event_{index}", "source": "设备接口"},
                "event_state": {"type": f"dynamic_state_{index}", "source": "状态接口"},
                "context_signals": [
                    {
                        "type": f"authorized_context_{index}",
                        "source": "用户授权上下文",
                        "availability": "available",
                        "authorization": "用户明确授权",
                        "freshness": "一分钟内",
                        "latency_ms": 100,
                        "confidence": 0.9,
                        "fallback": "退化为基础通知",
                    },
                    {
                        "type": f"device_context_{index}",
                        "source": "设备状态接口",
                        "availability": "available",
                        "authorization": "设备所有者授权",
                        "freshness": "实时",
                        "latency_ms": 80,
                        "confidence": 0.9,
                        "fallback": "不输出高确定性建议",
                    },
                ],
                "inference": f"推断动态事件 {index} 的上下文含义",
                "risk_or_value": f"减少第 {index} 类手动判断",
                "recommended_action": f"输出第 {index} 类可解释建议",
            },
            "competitor_gap_ids": ["signal_dynamic_gap"],
            "technical_assessment": {
                "data_requirements": ["设备事件与授权上下文"],
                "required_capabilities": ["事件关联"],
                "privacy_constraints": ["最小化处理授权数据"],
                "feasibility_summary": "当前接口可做最小验证。",
                "demo_validation_plan": "用授权样本验证输入到建议。",
            },
            "evidence_ids": [self.user_evidence_id, self.competitor_evidence_id],
        }


def _brief() -> ResearchBrief:
    return ResearchBrief(
        question="分析动态设备品类未来产品机会",
        category="动态设备",
        target_user="动态设备用户",
        region="US",
        scenarios=[],
    )


def _evidence(claim_type: EvidenceClaimType, url: str, excerpt: str) -> EvidenceIngest:
    return EvidenceIngest(
        source_url=url,
        source_type="webpage",
        title="Dynamic product research evidence",
        original_excerpt=excerpt,
        claim_type=claim_type,
        collected_at=datetime.now(UTC),
        status=EvidenceStatus.VERIFIED,
        confidence=0.9,
        authority_score=0.8,
        recency_score=0.8,
        diversity_score=0.8,
    )


def _user_artifact(evidence_id: str) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id="pending_user",
        task_id="task_user_upstream",
        artifact_type=ResearchAgentType.USER_RESEARCH,
        status=ResearchTaskStatus.COMPLETED,
        payload={
            "summary": "用户仍需解释设备事件。",
            "summary_evidence_ids": [evidence_id],
            "event_chains": [],
            "pain_points": [],
            "unmet_needs": [],
            "sample_biases": [],
            "research_gaps": [],
            "evidence_coverage": {},
        },
        evidence_ids=[evidence_id],
        quality_score=85,
    )


def _competitor_artifact(evidence_id: str) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id="pending_competitor",
        task_id="task_competitor_upstream",
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        status=ResearchTaskStatus.COMPLETED,
        payload={
            "schema_name": "competitor_synthesis_intelligence",
            "synthesis_status": "completed",
            "summary_evidence_ids": [evidence_id],
            "specialist_outputs": [{}, {}, {}],
            "product_profiles": [
                {
                    "scope_label": "动态竞品",
                    "strengths": [{"evidence_ids": [evidence_id]}],
                    "weaknesses": [],
                    "tradeoffs": [],
                }
            ],
            "comparative_insights": [],
            "opportunity_signals": [
                {"signal_id": "signal_dynamic_gap", "evidence_ids": [evidence_id]}
            ],
            "research_gaps": [],
            "coverage_matrix": [
                {
                    "scope_label": "动态竞品",
                    "official_product_evidence_ids": [evidence_id],
                    "price_channel_evidence_ids": [evidence_id],
                    "user_review_evidence_ids": [evidence_id],
                }
            ],
            "evidence_audit": {"status": "passed", "specialist_output_count": 3},
        },
        evidence_ids=[evidence_id],
        quality_score=88,
    )


async def _persist_upstream(
    database: Database,
    broker: ProjectEventBroker,
    project_id: str,
    agent_type: ResearchAgentType,
    artifact: ResearchArtifact,
) -> None:
    registry = AgentRegistry()
    registry.bind(agent_type, StaticArtifactAdapter(artifact))
    task = ResearchTask(
        task_id=artifact.task_id,
        project_id=project_id,
        agent_type=agent_type,
        goal="persist tested upstream artifact",
    )
    await AgentRuntimeGateway(database, registry, broker, "trace_upstream").execute(
        task,
        AgentContext(project_id=project_id, brief=_brief(), iteration=0),
    )


@pytest.mark.asyncio
async def test_product_technical_service_runs_model_and_persists_lineage() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    broker = ProjectEventBroker()
    try:
        now = datetime.now(UTC)
        async with database.session() as session:
            session.add(
                ProjectModel(
                    project_id="proj_product_agent",
                    status=ProjectStatus.RESEARCHING,
                    current_stage="product_technical",
                    progress=45,
                    brief_json=_brief().model_dump(mode="json"),
                    model_selection_json={
                        "default_model_id": "product-test:opportunity-model",
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
                "trace_evidence",
                broker,
            )
            user = await evidence_service.ingest(
                "proj_product_agent",
                _evidence(
                    EvidenceClaimType.USER_OPINION,
                    "https://users.example/dynamic",
                    "Users still interpret device events manually.",
                ),
            )
            competitor = await evidence_service.ingest(
                "proj_product_agent",
                _evidence(
                    EvidenceClaimType.VENDOR_CLAIM,
                    "https://vendor.example/dynamic",
                    "Current products report isolated events.",
                ),
            )
        user_id = user.evidence.evidence_id
        competitor_id = competitor.evidence.evidence_id
        await _persist_upstream(
            database,
            broker,
            "proj_product_agent",
            ResearchAgentType.USER_RESEARCH,
            _user_artifact(user_id),
        )
        await _persist_upstream(
            database,
            broker,
            "proj_product_agent",
            ResearchAgentType.COMPETITOR_RESEARCH,
            _competitor_artifact(competitor_id),
        )

        provider = ProductOpportunityProvider(user_id, competitor_id)
        providers = ModelProviderRegistry()
        providers.register(provider)
        catalog = ModelCatalog.from_json(
            json.dumps(
                [
                    {
                        "model_id": "product-test:opportunity-model",
                        "provider": "product-test",
                        "provider_model": "opportunity-model",
                        "display_name": "Product opportunity model",
                        "credential_env": "PRODUCT_TEST_KEY",
                        "capabilities": ["text", "structured_output"],
                    }
                ]
            ),
            default_model_id="product-test:opportunity-model",
        )
        gateway = ModelGateway(
            database,
            catalog,
            EnvironmentCredentialResolver({"PRODUCT_TEST_KEY": "local-test-secret"}),
            providers,
            max_retries=0,
        )
        prompts = PromptRegistry()
        register_product_technical_prompt(prompts)
        registry = AgentRegistry()
        registry.bind(
            ResearchAgentType.PRODUCT_TECHNICAL,
            ProductTechnicalModelAgentAdapter(
                gateway,
                prompts,
                ProjectModelSelectionResolver(database),
            ),
        )
        service = ProductTechnicalService(
            database,
            AgentRuntimeGateway(database, registry, broker, "trace_product_runtime"),
            ProductTechnicalEvidenceContextBuilder(
                database,
                max_items=10,
                max_excerpt_chars=2_000,
                max_total_chars=20_000,
            ),
        )

        artifact = await service.run("proj_product_agent")
        versions = await service.list_artifacts("proj_product_agent")
        stored = await ArtifactStore(database).list_versions(
            "proj_product_agent", "task_product_technical"
        )

        assert artifact.status is ResearchTaskStatus.COMPLETED
        assert artifact.payload.coverage.advancing_candidate_count == 3
        assert [candidate.name for candidate in artifact.payload.candidates] == [
            "动态未来机会 1",
            "动态未来机会 2",
            "动态未来机会 3",
        ]
        assert len(versions) == len(stored) == 1
        assert set(stored[0].input_artifact_ids) == {
            stored_id.artifact.artifact_id
            for stored_id in [
                await ArtifactStore(database).latest_by_type(
                    "proj_product_agent", ResearchAgentType.USER_RESEARCH.value
                ),
                await ArtifactStore(database).latest_by_type(
                    "proj_product_agent", ResearchAgentType.COMPETITOR_RESEARCH.value
                ),
            ]
            if stored_id is not None
        }
        assert len(provider.requests) == 1
        assert "动态设备" in provider.requests[0].messages[1].content
        assert "local-test-secret" not in provider.requests[0].messages[1].content
    finally:
        await database.dispose()
