"""A2A 专家子任务的持久化访问。"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import A2ATaskModel


class A2ATaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, task: A2ATaskModel) -> None:
        self.session.add(task)
        await self.session.flush()

    async def get(self, a2a_task_id: str) -> A2ATaskModel | None:
        return await self.session.get(A2ATaskModel, a2a_task_id)

    async def get_by_identity(
        self,
        project_id: str,
        parent_task_id: str,
        specialist_type: str,
    ) -> A2ATaskModel | None:
        statement = select(A2ATaskModel).where(
            A2ATaskModel.project_id == project_id,
            A2ATaskModel.parent_task_id == parent_task_id,
            A2ATaskModel.specialist_type == specialist_type,
        )
        return cast(A2ATaskModel | None, await self.session.scalar(statement))

    async def list_for_parent(
        self,
        project_id: str,
        parent_task_id: str,
    ) -> list[A2ATaskModel]:
        statement = (
            select(A2ATaskModel)
            .where(
                A2ATaskModel.project_id == project_id,
                A2ATaskModel.parent_task_id == parent_task_id,
            )
            .order_by(A2ATaskModel.specialist_type.asc())
        )
        return list(await self.session.scalars(statement))

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
