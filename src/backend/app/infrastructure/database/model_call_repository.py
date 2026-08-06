"""模型调用尝试与 Agent Run 用量审计仓储。"""

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import AgentRunModel, ModelCallModel


class ModelCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, model_call: ModelCallModel) -> None:
        self.session.add(model_call)
        await self.session.flush()

    async def get(self, model_call_id: str) -> ModelCallModel | None:
        return await self.session.get(ModelCallModel, model_call_id)

    async def list_for_run(self, agent_run_id: str) -> list[ModelCallModel]:
        statement: Select[tuple[ModelCallModel]] = (
            select(ModelCallModel)
            .where(ModelCallModel.agent_run_id == agent_run_id)
            .order_by(ModelCallModel.attempt_number.asc())
        )
        return list(await self.session.scalars(statement))

    async def require_run(self, agent_run_id: str) -> AgentRunModel:
        run = await self.session.get(AgentRunModel, agent_run_id)
        if run is None:
            raise ValueError("agent run does not exist")
        return run

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
