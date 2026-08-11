"""调研总管任务计划的确定性解析和依赖校验。"""

from collections import Counter
from collections.abc import Iterable

from app.workflows.contracts import (
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    WorkflowContractError,
)

PLANNED_AGENT_TYPES = (
    ResearchAgentType.USER_RESEARCH,
    ResearchAgentType.COMPETITOR_RESEARCH,
    ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
)


def parse_task_plan(manager_artifact: ResearchArtifact, project_id: str) -> list[ResearchTask]:
    raw_tasks = manager_artifact.payload.get("tasks")
    if not isinstance(raw_tasks, list):
        raise WorkflowContractError("research manager artifact must contain a tasks list")

    tasks = [ResearchTask.model_validate(item) for item in raw_tasks]
    _validate_identity(tasks, project_id)
    _validate_roles(tasks)
    _validate_dependencies(tasks)
    return tasks


def task_for_agent(
    task_plan: Iterable[ResearchTask],
    agent_type: ResearchAgentType,
) -> ResearchTask:
    matching = [task for task in task_plan if task.agent_type is agent_type]
    if len(matching) != 1:
        raise WorkflowContractError(
            f"task plan must contain exactly one task for {agent_type}; got {len(matching)}"
        )
    return matching[0]


def _validate_identity(tasks: list[ResearchTask], project_id: str) -> None:
    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise WorkflowContractError("task plan contains duplicate task ids")
    if any(task.project_id != project_id for task in tasks):
        raise WorkflowContractError("task plan contains a cross-project task")


def _validate_roles(tasks: list[ResearchTask]) -> None:
    counts = Counter(task.agent_type for task in tasks)
    expected = set(PLANNED_AGENT_TYPES)
    if set(counts) != expected or any(count != 1 for count in counts.values()):
        missing = sorted(agent.value for agent in expected - set(counts))
        unexpected = sorted(agent.value for agent in set(counts) - expected)
        raise WorkflowContractError(
            f"task plan role mismatch; missing={missing}, unexpected={unexpected}"
        )


def _validate_dependencies(tasks: list[ResearchTask]) -> None:
    by_agent = {task.agent_type: task for task in tasks}

    def require(agent: ResearchAgentType, dependencies: set[ResearchAgentType]) -> None:
        actual = set(by_agent[agent].depends_on)
        required_ids = {by_agent[dependency].task_id for dependency in dependencies}
        if not required_ids.issubset(actual):
            raise WorkflowContractError(
                f"{agent} is missing dependencies {sorted(required_ids - actual)}"
            )

    require(
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        {ResearchAgentType.USER_RESEARCH, ResearchAgentType.COMPETITOR_RESEARCH},
    )
