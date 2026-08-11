from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.agents.commercial_evaluation_v2 import CommercialEvaluationOutputValidator
from app.agents.red_team_policy_revision import (
    ChallengeResponseStatus,
    RedTeamChallenge,
    RedTeamChallengeCreate,
    RedTeamModelOutput,
    RedTeamOutputValidator,
    RedTeamRunCreate,
    RedTeamValidationError,
    RedTeamVerdict,
    challenge_id,
)
from app.agents.red_team_policy_revision.contracts import (
    REQUIRED_AUTOMATED_DIMENSIONS,
)
from app.agents.security_policy import SecurityPolicyCompiler
from app.application.research.red_team_policy_revision import (
    RedTeamPolicyRevisionService,
)
from app.application.source_recovery.gaps import AgentGapProjector
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.schemas.source_recovery import RecoverableAgentType
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchBudget,
    ResearchTask,
    ResearchTaskStatus,
)
from tests.unit.test_commercial_evaluation_v2 import _context as commercial_context
from tests.unit.test_commercial_evaluation_v2 import _output as commercial_output
from tests.unit.test_commercial_evaluation_v2 import _task as commercial_task
from tests.unit.test_security_policy_compiler import _output as policy_output
from tests.unit.test_security_policy_compiler import _task as policy_task


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_red_team_policy_revision_v2",
        project_id="proj_ecosystem",
        agent_type=ResearchAgentType.RED_TEAM,
        goal="Attack the current AI-native ecosystem policy.",
        budget=ResearchBudget(deadline_seconds=180),
    )


def _context() -> AgentContext:
    base = commercial_context()
    opportunity = base.upstream_artifacts[ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value]
    technical = base.upstream_artifacts[ResearchAgentType.TECHNICAL_FEASIBILITY.value]
    policy = SecurityPolicyCompiler().compile(
        policy_task(),
        AgentContext(
            project_id=base.project_id,
            brief=base.brief,
            iteration=0,
            upstream_artifacts={
                ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value: opportunity,
                ResearchAgentType.TECHNICAL_FEASIBILITY.value: technical,
            },
            selected_innovation_ids=base.selected_innovation_ids,
            evidence_context=base.evidence_context,
            research_handoff=base.research_handoff,
        ),
        policy_output(),
    )
    commercial = CommercialEvaluationOutputValidator().validate(
        commercial_task(), base, commercial_output()
    )
    competitor = ResearchArtifact(
        artifact_id="artifact_competitor_ecosystem",
        task_id="task_competitor_ecosystem",
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        status=ResearchTaskStatus.COMPLETED,
        payload={"schema_name": "competitor_ecosystem_analysis"},
        evidence_ids=["ev_one"],
        quality_score=90,
    )
    return AgentContext(
        project_id=base.project_id,
        brief=base.brief,
        iteration=0,
        upstream_artifacts={
            **base.upstream_artifacts,
            ResearchAgentType.COMPETITOR_RESEARCH.value: competitor,
            ResearchAgentType.SECURITY_POLICY.value: policy.to_research_artifact(),
            ResearchAgentType.COMMERCIAL_EVALUATION.value: commercial.to_research_artifact(),
        },
        selected_innovation_ids=base.selected_innovation_ids,
        evidence_context=base.evidence_context,
        research_handoff=base.research_handoff,
    )


def _dimensions(*, include_challenge: bool = False) -> list[str]:
    values = sorted(item.value for item in REQUIRED_AUTOMATED_DIMENSIONS)
    return [*values, "user_challenge"] if include_challenge else values


def _output() -> RedTeamModelOutput:
    return RedTeamModelOutput.model_validate(
        {
            "summary": "九个自动攻击维度均未发现阻断性问题。",
            "summary_evidence_ids": ["ev_one", "ev_device", "ev_market"],
            "attacked_dimensions": _dimensions(),
            "findings": [],
            "challenge_responses": [],
            "red_team_gaps": [],
            "fallback_plan": None,
            "unknowns": [],
        }
    )


def _finding(context: AgentContext, **updates: object) -> dict[str, object]:
    policy = context.upstream_artifacts[ResearchAgentType.SECURITY_POLICY.value]
    policy_id = str(policy.payload["policies"][0]["policy_id"])
    raw: dict[str, object] = {
        "dimension": "safety_failure",
        "severity": "medium",
        "title": "不确定状态下的干预仍然过强",
        "description": "策略在证据不足时仍可能通知照护者。",
        "evidence_ids": ["ev_device"],
        "affected_artifact_ids": [policy.artifact_id],
        "affected_agent_types": ["security_policy"],
        "affected_opportunity_ids": ["eco_dynamic_1"],
        "affected_policy_ids": [policy_id],
        "affected_scenario_ids": [],
        "required_actions": ["把不确定状态降级为本地开灯并重新验证。"],
        "requires_source_recovery": False,
        "requires_human_decision": False,
        "irreducible": False,
    }
    raw.update(updates)
    return raw


def test_backend_passes_only_after_all_automated_dimensions_are_attacked() -> None:
    artifact = RedTeamOutputValidator().validate(_task(), _context(), _output(), [])

    assert artifact.payload.verdict is RedTeamVerdict.PASS
    assert artifact.payload.coverage.required_dimension_count == 9
    assert artifact.payload.revision_requests == []


def test_backend_derives_revision_target_and_never_accepts_model_task_ids() -> None:
    context = _context()
    raw = _output().model_dump(mode="json")
    raw["findings"] = [_finding(context)]

    artifact = RedTeamOutputValidator().validate(
        _task(), context, RedTeamModelOutput.model_validate(raw), []
    )

    assert artifact.payload.verdict is RedTeamVerdict.REVISE
    revision = artifact.payload.revision_requests[0]
    assert revision.resume_from_agent == "security_policy"
    assert revision.affected_task_ids == [context.upstream_artifacts["security_policy"].task_id]


def test_unresolved_user_challenge_becomes_source_recovery_gap() -> None:
    context = _context()
    create = RedTeamChallengeCreate(
        question="老人不同意摄像头采集时，方案是否还能成立？",
        actor="coach",
    )
    challenge = RedTeamChallenge(
        challenge_id=challenge_id(create), **create.model_dump(mode="python")
    )
    finding = _finding(
        context,
        dimension="user_challenge",
        title="缺少无摄像头替代策略证据",
        required_actions=[],
        requires_source_recovery=True,
    )
    raw = _output().model_dump(mode="json")
    raw["attacked_dimensions"] = _dimensions(include_challenge=True)
    raw["findings"] = [finding]
    raw["challenge_responses"] = [
        {
            "challenge_id": challenge.challenge_id,
            "status": ChallengeResponseStatus.UNRESOLVED,
            "answer": "当前证据无法证明完全不使用摄像头时仍可达到同等安全目标。",
            "evidence_ids": ["ev_device"],
            "related_finding_indexes": [0],
        }
    ]
    raw["red_team_gaps"] = [
        {
            "question": "门磁和人体传感器是否足以覆盖该安全目标？",
            "reason": "需要无摄像头设备组合的企业能力资料。",
            "severity": "medium",
            "dimension": "user_challenge",
            "recommended_source_types": ["enterprise_document"],
            "required_evidence_types": ["device_capability"],
            "affected_agent_types": ["security_policy"],
            "affected_opportunity_ids": ["eco_dynamic_1"],
        }
    ]

    artifact = RedTeamOutputValidator().validate(
        _task(), context, RedTeamModelOutput.model_validate(raw), [challenge]
    )

    assert artifact.payload.verdict is RedTeamVerdict.NEEDS_MORE_EVIDENCE
    assert artifact.payload.red_team_gaps[0].gap_id.startswith("gap_")
    assert artifact.payload.challenge_responses[0].related_finding_ids
    projected = AgentGapProjector().project(
        artifact.to_research_artifact(), RecoverableAgentType.RED_TEAM
    )
    assert projected[0].affected_agent_types == ["security_policy"]


def test_rejected_scope_requires_a_safe_fallback_instead_of_empty_output() -> None:
    context = _context()
    raw = _output().model_dump(mode="json")
    raw["findings"] = [
        _finding(
            context,
            severity="critical",
            required_actions=[],
            irreducible=True,
        )
    ]

    with pytest.raises(RedTeamValidationError, match="fallback"):
        RedTeamOutputValidator().validate(
            _task(), context, RedTeamModelOutput.model_validate(raw), []
        )


def test_second_version_reports_resolved_findings() -> None:
    context = _context()
    first_raw = _output().model_dump(mode="json")
    first_raw["findings"] = [_finding(context)]
    first = RedTeamOutputValidator().validate(
        _task(), context, RedTeamModelOutput.model_validate(first_raw), []
    )
    second_context = context.model_copy(
        update={
            "iteration": 1,
            "upstream_artifacts": {
                **context.upstream_artifacts,
                "previous_red_team": first.to_research_artifact(),
            },
        }
    )

    second = RedTeamOutputValidator().validate(_task(), second_context, _output(), [])

    assert second.payload.version_diff.previous_artifact_id == first.artifact_id
    assert second.payload.version_diff.resolved_finding_ids == [
        first.payload.findings[0].finding_id
    ]


def test_user_challenge_targets_must_exist_before_model_execution() -> None:
    request = RedTeamRunCreate(
        challenges=[
            RedTeamChallengeCreate(
                question="这个旧策略是否仍然有效？",
                actor="reviewer",
                target_policy_ids=["policy_old"],
            )
        ]
    )

    with pytest.raises(AppError) as exc_info:
        RedTeamPolicyRevisionService._validated_challenges(
            request,
            artifact_ids={"artifact_current"},
            policy_ids={"policy_current"},
            scenario_ids={"scenario_current"},
        )

    assert exc_info.value.code == "RED_TEAM_CHALLENGE_SCOPE_INVALID"


def test_red_team_rejects_evidence_outside_bounded_context() -> None:
    raw = deepcopy(_output().model_dump(mode="json"))
    raw["summary_evidence_ids"] = ["ev_not_allowed"]

    with pytest.raises(RedTeamValidationError, match="outside"):
        RedTeamOutputValidator().validate(
            _task(), _context(), RedTeamModelOutput.model_validate(raw), []
        )


def test_model_cannot_choose_verdict_revision_request_or_score() -> None:
    for field, value in (
        ("verdict", "pass"),
        ("revision_requests", []),
        ("quality_score", 100),
    ):
        raw = deepcopy(_output().model_dump(mode="json"))
        raw[field] = value
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RedTeamModelOutput.model_validate(raw)


def test_public_routes_and_checked_in_openapi_expose_red_team_v2() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]
    route = "/api/v1/projects/{project_id}/agents/red-team-policy-revision"
    assert route in paths
    assert f"{route}/artifacts" in paths

    repository_root = Path(__file__).resolve().parents[4]
    document = yaml.safe_load(
        (repository_root / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )
    schema = document["paths"]["/projects/{project_id}/agents/red-team-policy-revision"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/RedTeamRunCreate"}
    assert set(document["components"]["schemas"]["RedTeamVerdict"]["enum"]) == {
        item.value for item in RedTeamVerdict
    }
