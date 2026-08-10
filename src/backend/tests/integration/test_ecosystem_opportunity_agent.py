import json
from datetime import UTC, datetime

import pytest

from app.agents.ecosystem_opportunity import (
    EcosystemOpportunityContextBuilder,
    EcosystemOpportunityModelAgentAdapter,
    register_ecosystem_opportunity_prompt,
)
from app.application.device_capabilities import DeviceCapabilityService
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
from app.application.research import EcosystemOpportunityService
from app.application.runtime import AgentRegistry, AgentRuntimeGateway, ArtifactStore
from app.infrastructure.database import Database
from app.infrastructure.database.device_capability_repository import (
    DeviceCapabilityRepository,
)
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.device_capability import CatalogDeviceCreate
from app.schemas.evidence import EvidenceClaimType, EvidenceIngest, EvidenceStatus
from app.schemas.project import ProjectStatus
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)
from tests.research_brief import home_safety_brief


class StaticArtifactAdapter:
    adapter_type = "static_ecosystem_upstream"

    def __init__(self, artifact: ResearchArtifact) -> None:
        self.artifact = artifact

    async def execute(self, invocation) -> object:  # type: ignore[no-untyped-def]
        return self.artifact.model_copy(
            update={
                "task_id": invocation.task.task_id,
                "artifact_type": invocation.task.agent_type.value,
            }
        )


class EcosystemOpportunityProvider:
    provider_id = "ecosystem-test"

    def __init__(self, user_id: str, competitor_id: str, capability_id: str) -> None:
        self.user_id = user_id
        self.competitor_id = competitor_id
        self.capability_id = capability_id
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        return ProviderModelResult(
            output={
                "summary": "用户需要连续理解，竞品仍存在跨设备状态缺口。",
                "summary_evidence_ids": [self.user_id, self.competitor_id],
                "opportunities": [self._candidate(index) for index in range(1, 4)],
                "portfolio_gaps": [],
                "unknowns": [],
            },
            usage=ModelUsage(input_tokens=1_500, output_tokens=1_000),
            provider_request_id="provider-ecosystem-opportunity",
        )

    def _candidate(self, index: int) -> dict[str, object]:
        return {
            "opportunity_id": f"ecosystem_dynamic_{index}",
            "name": f"证据驱动生态机会 {index}",
            "scope_level": "ecosystem_service",
            "target_user": {
                "persona_ids": ["authorized_household"],
                "description": "明确授权家庭安防研究的家庭",
            },
            "problem": {
                "pain_ids": ["manual_event_joining"],
                "description": "用户需要手动理解多个孤立事件",
            },
            "safety_goal": f"持续理解第 {index} 类安全目标",
            "ecosystem_blueprint": {
                "required_device_roles": [
                    {
                        "role_id": f"sensor_{index}",
                        "role_type": "primary_perception",
                        "description": "提供授权安全事件",
                        "required_capabilities": [],
                        "optional": False,
                        "evidence_ids": [],
                    },
                    {
                        "role_id": f"hub_{index}",
                        "role_type": "local_reasoning_hub",
                        "description": "关联连续事件",
                        "required_capabilities": ["本地事件推理"],
                        "optional": False,
                        "evidence_ids": [self.capability_id],
                    },
                ],
                "required_capabilities": ["本地事件推理"],
                "cross_device_information_flows": [
                    {
                        "flow_id": f"event_flow_{index}",
                        "from_role_id": f"sensor_{index}",
                        "to_role_id": f"hub_{index}",
                        "data_type": "authorized_event_metadata",
                        "purpose": "维护连续家庭安全状态",
                        "privacy_constraints": ["最少化事件元数据"],
                        "fallback": "退化为基础通知",
                    }
                ],
                "deployment_target": "hybrid",
                "privacy_boundary": "原始媒体默认保留在本地",
                "permission_boundary": "高影响动作需要人工批准",
                "offline_behavior": "离线时只运行低风险规则",
                "fallback_behavior": "证据不足时询问用户",
                "known_blind_spots": ["设备离线时上下文不完整"],
            },
            "ai_native_case": {
                "open_ended_goal": "持续守护家庭安全",
                "why_fixed_rules_are_insufficient": "家庭设备和习惯持续变化",
                "model_responsibilities": ["解释事件序列和不确定性"],
                "deterministic_responsibilities": ["执行授权和动作边界"],
                "ai_removal_test": {
                    "core_value_survives_without_ai": False,
                    "rationale": "移除模型后只能做固定检测通知",
                    "lost_capabilities_without_ai": ["开放目标到策略转换"],
                    "evidence_ids": [self.user_id],
                },
                "learning_or_revision_loop": ["验证失败后修订策略"],
                "safety_constraints": ["不做医疗诊断"],
            },
            "competitor_gap_ids": ["signal_temporal_gap"],
            "technical_hypotheses": [],
            "commercial_hypotheses": ["付费意愿需要后续商业验证"],
            "validation_plan": {
                "validation_goal": "部署前验证策略安全性",
                "required_scenario_types": ["normal", "failure", "adversarial"],
                "success_conditions": ["正常事件不触发高风险动作"],
                "failure_conditions": ["高风险事件未被升级"],
                "required_data": ["授权事件或模拟事件"],
                "human_review_points": ["启用策略之前"],
            },
            "evidence_ids": [self.user_id, self.competitor_id, self.capability_id],
        }


def _evidence(claim_type: EvidenceClaimType, url: str, excerpt: str) -> EvidenceIngest:
    return EvidenceIngest(
        source_url=url,
        source_type="webpage",
        title="Ecosystem research evidence",
        original_excerpt=excerpt,
        claim_type=claim_type,
        collected_at=datetime.now(UTC),
        status=EvidenceStatus.VERIFIED,
        confidence=0.9,
        authority_score=0.9,
        recency_score=0.8,
        diversity_score=0.8,
    )


def _user_artifact(evidence_id: str) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id="pending_user_ecosystem",
        task_id="task_user_research",
        artifact_type=ResearchAgentType.USER_RESEARCH,
        status=ResearchTaskStatus.COMPLETED,
        payload={
            "summary_evidence_ids": [evidence_id],
            "event_chains": [],
            "pain_points": [],
            "unmet_needs": [],
            "sample_biases": [],
            "research_gaps": [],
            "evidence_coverage": {},
        },
        evidence_ids=[evidence_id],
        quality_score=88,
    )


def _competitor_artifact(evidence_id: str) -> ResearchArtifact:
    dimensions = {
        name: "supported" if name == "safety_goal_coverage" else "unknown"
        for name in (
            "safety_goal_coverage",
            "cross_device_orchestration",
            "temporal_state_understanding",
            "active_perception",
            "uncertainty_handling",
            "intervention_ladder",
            "local_cloud_partition",
            "privacy_and_consent",
            "offline_fallback",
            "caregiver_workflow",
            "failure_recovery",
            "business_model",
        )
    }
    return ResearchArtifact(
        artifact_id="pending_competitor_ecosystem",
        task_id="task_competitor_ecosystem",
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        schema_version="2.0",
        status=ResearchTaskStatus.PARTIAL,
        payload={
            "schema_name": "competitor_ecosystem_analysis",
            "synthesis_status": "partial",
            "summary_evidence_ids": [evidence_id],
            "specialist_outputs": [{}, {}, {}],
            "ecosystem_profiles": [
                {
                    "ecosystem_label": "eufy Security",
                    "product_scope_labels": ["eufy evidence catalog"],
                    "assessments": [
                        {
                            "dimension": "safety_goal_coverage",
                            "evidence_ids": [evidence_id],
                        }
                    ],
                }
            ],
            "comparison_insights": [],
            "opportunity_signals": [
                {"signal_id": "signal_temporal_gap", "evidence_ids": [evidence_id]}
            ],
            "research_gaps": [
                {
                    "ecosystem_label": "eufy Security",
                    "dimension": "temporal_state_understanding",
                    "question": "哪些证据能证明生态维护连续家庭状态？",
                }
            ],
            "coverage_matrix": [
                {
                    "ecosystem_label": "eufy Security",
                    "dimension_statuses": dimensions,
                    "mapped_products": ["eufy evidence catalog"],
                    "evidence_ids": [evidence_id],
                }
            ],
            "evidence_audit": {"status": "passed_with_gaps", "specialist_output_count": 3},
        },
        evidence_ids=[evidence_id],
        quality_score=78,
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
    await AgentRuntimeGateway(database, registry, broker, "trace_upstream").execute(
        ResearchTask(
            task_id=artifact.task_id,
            project_id=project_id,
            agent_type=agent_type,
            goal="persist ecosystem test upstream",
        ),
        AgentContext(project_id=project_id, brief=home_safety_brief(), iteration=0),
    )


def _service(
    database: Database,
    broker: ProjectEventBroker,
    provider: EcosystemOpportunityProvider,
) -> EcosystemOpportunityService:
    providers = ModelProviderRegistry()
    providers.register(provider)
    catalog = ModelCatalog.from_json(
        json.dumps(
            [
                {
                    "model_id": "ecosystem-test:opportunity-model",
                    "provider": "ecosystem-test",
                    "provider_model": "opportunity-model",
                    "display_name": "Ecosystem opportunity model",
                    "credential_env": "ECOSYSTEM_TEST_KEY",
                    "capabilities": ["text", "structured_output"],
                }
            ]
        ),
        default_model_id="ecosystem-test:opportunity-model",
    )
    gateway = ModelGateway(
        database,
        catalog,
        EnvironmentCredentialResolver({"ECOSYSTEM_TEST_KEY": "local-test-secret"}),
        providers,
        max_retries=0,
    )
    prompts = PromptRegistry()
    register_ecosystem_opportunity_prompt(prompts)
    registry = AgentRegistry()
    registry.bind(
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        EcosystemOpportunityModelAgentAdapter(
            gateway,
            prompts,
            ProjectModelSelectionResolver(database),
        ),
    )
    return EcosystemOpportunityService(
        database,
        AgentRuntimeGateway(database, registry, broker, "trace_ecosystem_runtime"),
        EcosystemOpportunityContextBuilder(
            database,
            max_items=20,
            max_excerpt_chars=2_000,
            max_total_chars=30_000,
        ),
    )


@pytest.mark.asyncio
async def test_service_runs_real_model_chain_with_ecosystem_and_capability_inputs() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    broker = ProjectEventBroker()
    project_id = "proj_ecosystem_agent"
    try:
        now = datetime.now(UTC)
        async with database.session() as session:
            session.add(
                ProjectModel(
                    project_id=project_id,
                    status=ProjectStatus.RESEARCHING,
                    current_stage="ecosystem_opportunity",
                    progress=60,
                    brief_json=home_safety_brief().model_dump(mode="json"),
                    model_selection_json={
                        "default_model_id": "ecosystem-test:opportunity-model",
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
                "trace_ecosystem_evidence",
                broker,
            )
            user = await evidence_service.ingest(
                project_id,
                _evidence(
                    EvidenceClaimType.USER_OPINION,
                    "https://users.example/ecosystem",
                    "Users manually join isolated safety notifications.",
                ),
            )
            competitor = await evidence_service.ingest(
                project_id,
                _evidence(
                    EvidenceClaimType.TECHNICAL_FACT,
                    "https://competitor.example/ecosystem",
                    "Cross-device temporal state remains insufficiently documented.",
                ),
            )
            identity = await evidence_service.ingest(
                project_id,
                _evidence(
                    EvidenceClaimType.PRODUCT_IDENTITY,
                    "https://eufy.example/homebase",
                    "The documented local hub is HomeBase S380.",
                ),
            )
            capability = await evidence_service.ingest(
                project_id,
                _evidence(
                    EvidenceClaimType.CAPABILITY,
                    "https://eufy.example/homebase/capability",
                    "HomeBase S380 supports local event reasoning.",
                ),
            )
            capability_service = DeviceCapabilityService(
                DeviceCapabilityRepository(session),
                ProjectRepository(session),
                broker,
                "trace_device_graph",
            )
            await capability_service.create_catalog_device(
                project_id,
                CatalogDeviceCreate.model_validate(
                    {
                        "manufacturer": "eufy",
                        "product_name": "HomeBase",
                        "model": "S380",
                        "category": "local_hub",
                        "lifecycle_status": "active",
                        "identity_evidence_ids": [identity.evidence.evidence_id],
                        "capabilities": [
                            {
                                "capability_key": "local.event_reasoning",
                                "capability_name": "本地事件推理",
                                "kind": "compute",
                                "assertion": "supported",
                                "availability": "available",
                                "confidence": 0.9,
                                "evidence_ids": [capability.evidence.evidence_id],
                                "data_scope": "homebase_local",
                                "authorization_required": True,
                                "offline_support": "degraded",
                                "fallback": "仅发送基础通知",
                            }
                        ],
                    }
                ),
            )
        await _persist_upstream(
            database,
            broker,
            project_id,
            ResearchAgentType.USER_RESEARCH,
            _user_artifact(user.evidence.evidence_id),
        )
        await _persist_upstream(
            database,
            broker,
            project_id,
            ResearchAgentType.COMPETITOR_RESEARCH,
            _competitor_artifact(competitor.evidence.evidence_id),
        )
        provider = EcosystemOpportunityProvider(
            user.evidence.evidence_id,
            competitor.evidence.evidence_id,
            capability.evidence.evidence_id,
        )
        service = _service(database, broker, provider)

        artifact = await service.run(project_id)
        versions = await service.list_artifacts(project_id)
        stored = await ArtifactStore(database).list_versions(
            project_id, "task_ecosystem_opportunity"
        )

        assert artifact.status is ResearchTaskStatus.PARTIAL
        assert artifact.payload.coverage.advancing_candidate_count == 3
        assert artifact.payload.coverage.ecosystem_service_count == 3
        assert len(versions) == len(stored) == 1
        assert len(provider.requests) == 1
        prompt = provider.requests[0].messages[1].content
        assert "本地事件推理" in prompt
        assert "competitor_ecosystem_analysis" in prompt
        assert "local-test-secret" not in prompt
        assert set(stored[0].input_artifact_ids) == {
            item.artifact.artifact_id
            for item in (
                await ArtifactStore(database).latest_by_type(
                    project_id, ResearchAgentType.USER_RESEARCH.value
                ),
                await ArtifactStore(database).latest_by_type(
                    project_id, ResearchAgentType.COMPETITOR_RESEARCH.value
                ),
            )
            if item is not None
        }
    finally:
        await database.dispose()
