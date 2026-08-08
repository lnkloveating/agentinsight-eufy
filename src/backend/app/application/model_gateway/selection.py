"""从项目持久化策略解析每类 Agent 应使用的模型。"""

from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.session import Database
from app.schemas.model import ModelSelection
from app.workflows.contracts import ResearchAgentType


class ModelSelectionResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ProjectModelSelectionResolver:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def resolve(self, project_id: str, agent_type: ResearchAgentType) -> str:
        return await self.resolve_for_key(project_id, agent_type.value)

    async def resolve_for_key(self, project_id: str, agent_key: str) -> str:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
        if project is None:
            raise ModelSelectionResolutionError(
                "PROJECT_NOT_FOUND", "model selection project does not exist"
            )
        if project.model_selection_json is None:
            raise ModelSelectionResolutionError(
                "MODEL_SELECTION_MISSING", "project has no model selection"
            )
        selection = ModelSelection.model_validate(project.model_selection_json)
        return selection.agent_overrides.get(agent_key, selection.default_model_id)
