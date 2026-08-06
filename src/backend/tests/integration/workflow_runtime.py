"""仅供工作流测试使用的确定性 Runtime；生产代码不会导入本模块。"""

from collections import Counter

from app.workflows.contracts import (
    AgentContext,
    RedTeamDirective,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)


class TestAgentRuntime:
    __test__ = False

    def __init__(
        self,
        *,
        evidence_ready_on_attempt: int = 1,
        fail_once: set[ResearchAgentType] | None = None,
    ) -> None:
        self.evidence_ready_on_attempt = evidence_ready_on_attempt
        self.fail_once = set(fail_once or set())
        self.calls: list[ResearchAgentType] = []
        self.call_counts: Counter[ResearchAgentType] = Counter()
        self.contexts: dict[ResearchAgentType, AgentContext] = {}

    async def execute(
        self,
        task: ResearchTask,
        context: AgentContext,
    ) -> ResearchArtifact:
        self.calls.append(task.agent_type)
        self.call_counts[task.agent_type] += 1
        self.contexts[task.agent_type] = context
        if task.agent_type in self.fail_once:
            self.fail_once.remove(task.agent_type)
            raise RuntimeError(f"planned failure:{task.agent_type}")

        payload: dict[str, object] = {}
        evidence_ids: list[str] = []
        status = ResearchTaskStatus.COMPLETED
        if task.agent_type is ResearchAgentType.RESEARCH_MANAGER:
            payload = {"tasks": [item.model_dump(mode="json") for item in _task_plan(task)]}
        elif task.agent_type in {
            ResearchAgentType.USER_RESEARCH,
            ResearchAgentType.COMPETITOR_RESEARCH,
        }:
            if self.call_counts[task.agent_type] < self.evidence_ready_on_attempt:
                status = ResearchTaskStatus.PARTIAL
            else:
                evidence_ids = [f"ev_test_{task.agent_type}"]
                payload = {"findings": [f"finding:{task.agent_type}"]}
        elif task.agent_type is ResearchAgentType.PRODUCT_TECHNICAL:
            evidence_ids = _upstream_evidence(context)
            payload = {"innovation_ids": ["inv_one", "inv_two", "inv_three"]}
        elif task.agent_type is ResearchAgentType.COMMERCIAL_EVALUATION:
            evidence_ids = _upstream_evidence(context)
            payload = {"assessed_innovation_ids": ["inv_one", "inv_two", "inv_three"]}
        elif task.agent_type is ResearchAgentType.RED_TEAM:
            evidence_ids = _upstream_evidence(context)
            payload = {
                "directive": RedTeamDirective(
                    decision="pass",
                    severity="medium",
                    required_actions=[],
                ).model_dump(mode="json")
            }
        elif task.agent_type is ResearchAgentType.CANDIDATE_SYNTHESIS:
            evidence_ids = _upstream_evidence(context)
            payload = {
                "innovation_ids": ["inv_one", "inv_two", "inv_three"],
                "recommendation": "investigate",
            }
        elif task.agent_type is ResearchAgentType.VALIDATION:
            evidence_ids = _upstream_evidence(context)
            payload = {"status": "test_validation_completed"}
        elif task.agent_type is ResearchAgentType.FINAL_SYNTHESIS:
            evidence_ids = _upstream_evidence(context)
            payload = {"recommendation": "investigate"}

        return ResearchArtifact(
            artifact_id=f"artifact_{task.task_id}_{self.call_counts[task.agent_type]}",
            task_id=task.task_id,
            artifact_type=task.agent_type,
            status=status,
            payload=payload,
            evidence_ids=evidence_ids,
            quality_score=90 if status is ResearchTaskStatus.COMPLETED else 70,
        )


def _task_plan(manager_task: ResearchTask) -> list[ResearchTask]:
    project_id = manager_task.project_id
    user = _task(project_id, "user", ResearchAgentType.USER_RESEARCH)
    competitor = _task(project_id, "competitor", ResearchAgentType.COMPETITOR_RESEARCH)
    product = _task(
        project_id,
        "product",
        ResearchAgentType.PRODUCT_TECHNICAL,
        [user.task_id, competitor.task_id],
    )
    commercial = _task(
        project_id,
        "commercial",
        ResearchAgentType.COMMERCIAL_EVALUATION,
        [product.task_id],
    )
    red_team = _task(
        project_id,
        "redteam",
        ResearchAgentType.RED_TEAM,
        [commercial.task_id],
    )
    candidate = _task(
        project_id,
        "candidate",
        ResearchAgentType.CANDIDATE_SYNTHESIS,
        [red_team.task_id],
    )
    validation = _task(
        project_id,
        "validation",
        ResearchAgentType.VALIDATION,
        [candidate.task_id],
    )
    final = _task(
        project_id,
        "final",
        ResearchAgentType.FINAL_SYNTHESIS,
        [validation.task_id],
    )
    return [user, competitor, product, commercial, red_team, candidate, validation, final]


def _task(
    project_id: str,
    suffix: str,
    agent_type: ResearchAgentType,
    depends_on: list[str] | None = None,
) -> ResearchTask:
    return ResearchTask(
        task_id=f"task_{project_id}_{suffix}",
        project_id=project_id,
        agent_type=agent_type,
        goal=f"test goal:{agent_type}",
        required_artifacts=[agent_type],
        depends_on=depends_on or [],
        acceptance_checks=["schema_valid"],
    )


def _upstream_evidence(context: AgentContext) -> list[str]:
    return sorted(
        {
            evidence_id
            for artifact in context.upstream_artifacts.values()
            for evidence_id in artifact.evidence_ids
        }
    )
