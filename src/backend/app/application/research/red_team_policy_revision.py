"""Application service for evidence-bound Red Team Policy Revision v2."""

from __future__ import annotations

from app.agents.policy_verification import PolicyVerificationArtifact
from app.agents.red_team_policy_revision import (
    RedTeamArtifact,
    RedTeamChallenge,
    RedTeamContextBuilder,
    RedTeamRunCreate,
    challenge_id,
)
from app.agents.security_policy import SecurityPolicyArtifact
from app.application.runtime import (
    AgentRuntimeGateway,
    ArtifactStore,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.core.errors import AppError
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.session import Database
from app.infrastructure.database.source_recovery_repository import (
    SourceRecoveryRepository,
)
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)
from app.workflows.handoff import build_research_handoff

RED_TEAM_POLICY_REVISION_TASK_ID = "task_red_team_policy_revision_v2"
_REQUIRED_UPSTREAM = (
    ResearchAgentType.USER_RESEARCH,
    ResearchAgentType.COMPETITOR_RESEARCH,
    ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
    ResearchAgentType.TECHNICAL_FEASIBILITY,
    ResearchAgentType.SECURITY_POLICY,
    ResearchAgentType.POLICY_VERIFICATION,
    ResearchAgentType.COMMERCIAL_EVALUATION,
)


class RedTeamPolicyRevisionService:
    def __init__(
        self,
        database: Database,
        runtime: AgentRuntimeGateway,
        context_builder: RedTeamContextBuilder,
    ) -> None:
        self.database = database
        self.runtime = runtime
        self.context_builder = context_builder
        self.artifact_store = ArtifactStore(database)

    async def run(self, project_id: str, request: RedTeamRunCreate) -> RedTeamArtifact:
        project = await self._require_runnable_project(project_id)
        stored = {
            item: await self.artifact_store.latest_by_type(project_id, item.value)
            for item in _REQUIRED_UPSTREAM
        }
        missing = [item.value for item, value in stored.items() if value is None]
        if missing:
            raise AppError(
                code="RED_TEAM_UPSTREAM_REQUIRED",
                message="必须先完成用户、竞品、生态机会、技术、策略、验证和商业分析。",
                status_code=409,
                details={"missing_agent_types": missing},
            )
        artifacts = {item: value.artifact for item, value in stored.items() if value is not None}
        policy = SecurityPolicyArtifact.from_research_artifact(
            artifacts[ResearchAgentType.SECURITY_POLICY]
        )
        verification = PolicyVerificationArtifact.from_research_artifact(
            artifacts[ResearchAgentType.POLICY_VERIFICATION]
        )
        challenges = self._validated_challenges(
            request,
            set(value.artifact_id for value in artifacts.values()),
            {item.policy_id for item in policy.payload.policies},
            {item.scenario_id for item in verification.payload.scenarios},
        )
        previous_versions = await self.artifact_store.list_versions(
            project_id, RED_TEAM_POLICY_REVISION_TASK_ID
        )
        previous = previous_versions[-1].artifact if previous_versions else None
        supplemental = await self._resolved_supplemental_evidence_ids(
            project_id, [item.artifact.artifact_id for item in previous_versions]
        )
        research_artifacts = {
            item.value: artifacts[item]
            for item in (
                ResearchAgentType.USER_RESEARCH,
                ResearchAgentType.COMPETITOR_RESEARCH,
            )
        }
        handoff = build_research_handoff(research_artifacts)
        evidence_context = await self.context_builder.build(
            project_id,
            handoff,
            list(artifacts.values()),
            supplemental,
        )
        selected = list(dict.fromkeys(policy.payload.selected_opportunity_ids))
        task = ResearchTask(
            task_id=RED_TEAM_POLICY_REVISION_TASK_ID,
            project_id=project_id,
            agent_type=ResearchAgentType.RED_TEAM,
            goal=("攻击当前 AI 原生家庭安防策略，回答用户质疑，并生成证据约束的定向返工要求。"),
            scope={
                "opportunity_ids": selected,
                "challenges": [item.model_dump(mode="json") for item in challenges],
            },
            required_artifacts=[item.value for item in _REQUIRED_UPSTREAM],
            evidence_rules=EvidenceRules(citation_required=True),
            budget=ResearchBudget(
                max_pages=evidence_context.included_evidence_count,
                max_iterations=2,
                deadline_seconds=180,
            ),
            depends_on=[artifacts[ResearchAgentType.COMMERCIAL_EVALUATION].task_id],
            acceptance_checks=[
                "all_attack_dimensions_covered",
                "all_factual_findings_evidence_bound",
                "all_user_challenges_answered_once",
                "verdict_computed_by_backend",
                "retry_targets_derived_from_current_artifacts",
                "rejected_scope_has_safe_fallback",
            ],
        )
        upstream = {item.value: artifact for item, artifact in artifacts.items()}
        if previous is not None:
            upstream["previous_red_team"] = previous
        context = AgentContext(
            project_id=project_id,
            brief=ResearchBrief.model_validate(project.brief_json),
            iteration=len(previous_versions),
            upstream_artifacts=upstream,
            selected_innovation_ids=selected,
            evidence_context=evidence_context,
            research_handoff=handoff,
        )
        try:
            artifact = await self.runtime.execute(task, context)
        except RuntimeGatewayError as exc:
            raise self._public_runtime_error(exc) from exc
        return RedTeamArtifact.from_research_artifact(artifact)

    async def list_artifacts(self, project_id: str) -> list[RedTeamArtifact]:
        await self._require_project(project_id)
        versions = await self.artifact_store.list_versions(
            project_id, RED_TEAM_POLICY_REVISION_TASK_ID
        )
        return [RedTeamArtifact.from_research_artifact(item.artifact) for item in versions]

    @staticmethod
    def _validated_challenges(
        request: RedTeamRunCreate,
        artifact_ids: set[str],
        policy_ids: set[str],
        scenario_ids: set[str],
    ) -> list[RedTeamChallenge]:
        challenges = [
            RedTeamChallenge(
                challenge_id=challenge_id(item),
                **item.model_dump(mode="python"),
            )
            for item in request.challenges
        ]
        ids = [item.challenge_id for item in challenges]
        if len(ids) != len(set(ids)):
            raise AppError(
                code="RED_TEAM_DUPLICATE_CHALLENGE",
                message="相同的用户质疑不能在一次红队运行中重复提交。",
                status_code=422,
            )
        unknown_artifacts = sorted(
            {value for item in challenges for value in item.target_artifact_ids} - artifact_ids
        )
        unknown_policies = sorted(
            {value for item in challenges for value in item.target_policy_ids} - policy_ids
        )
        unknown_scenarios = sorted(
            {value for item in challenges for value in item.target_scenario_ids} - scenario_ids
        )
        if unknown_artifacts or unknown_policies or unknown_scenarios:
            raise AppError(
                code="RED_TEAM_CHALLENGE_SCOPE_INVALID",
                message="用户质疑引用了当前版本不存在的 Artifact、Policy 或 Scenario。",
                status_code=422,
                details={
                    "unknown_artifact_ids": unknown_artifacts,
                    "unknown_policy_ids": unknown_policies,
                    "unknown_scenario_ids": unknown_scenarios,
                },
            )
        return challenges

    async def _resolved_supplemental_evidence_ids(
        self, project_id: str, artifact_ids: list[str]
    ) -> list[str]:
        evidence_ids: list[str] = []
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            for artifact_id in artifact_ids:
                for recovery in await repository.list_resolved_for_artifact(
                    project_id, artifact_id
                ):
                    for submission in recovery.submissions:
                        evidence_ids.extend(submission.evidence_ids_json)
        return list(dict.fromkeys(evidence_ids))

    async def _require_runnable_project(self, project_id: str) -> ProjectModel:
        project = await self._require_project(project_id)
        if project.status not in {
            ProjectStatus.RESEARCHING.value,
            ProjectStatus.SUPPLEMENTING_RESEARCH.value,
        }:
            raise AppError(
                code="RED_TEAM_PROJECT_NOT_READY",
                message="项目必须先通过 Research Brief 审批。",
                status_code=409,
                details={"project_id": project_id, "status": project.status},
            )
        return project

    async def _require_project(self, project_id: str) -> ProjectModel:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
        if project is None:
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )
        return project

    @staticmethod
    def _public_runtime_error(error: RuntimeGatewayError) -> AppError:
        if error.code is RuntimeErrorCode.TIMEOUT:
            status_code, code = 504, "RED_TEAM_TIMEOUT"
        elif error.code is RuntimeErrorCode.CANCELLED:
            status_code, code = 409, "RED_TEAM_CANCELLED"
        elif error.code in {
            RuntimeErrorCode.DEPENDENCY_MISSING,
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
        }:
            status_code, code = 503, "RED_TEAM_DEPENDENCY_UNAVAILABLE"
        elif error.code in {
            RuntimeErrorCode.ARTIFACT_INVALID,
            RuntimeErrorCode.SCHEMA_INVALID,
        }:
            status_code, code = 422, "RED_TEAM_OUTPUT_INVALID"
        else:
            status_code, code = 502, "RED_TEAM_FAILED"
        return AppError(
            code=code,
            message="红队未能生成通过证据和范围校验的审查结果。",
            status_code=status_code,
            details={
                "agent_run_id": error.agent_run_id,
                "runtime_error_code": error.code,
                "retryable": error.retryable,
                **error.details,
            },
        )
