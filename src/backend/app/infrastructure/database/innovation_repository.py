"""Innovation 的数据库仓储。"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import InnovationModel, ProjectModel


class InnovationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def project_exists(self, project_id: str) -> bool:
        return await self.session.get(ProjectModel, project_id) is not None

    async def add(self, model: InnovationModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def get(self, project_id: str, innovation_id: str) -> InnovationModel | None:
        statement = select(InnovationModel).where(
            InnovationModel.project_id == project_id,
            InnovationModel.innovation_id == innovation_id,
        )
        return cast(InnovationModel | None, await self.session.scalar(statement))

    async def list_by_project(self, project_id: str) -> list[InnovationModel]:
        statement = (
            select(InnovationModel)
            .where(InnovationModel.project_id == project_id)
            .order_by(InnovationModel.final_score.desc(), InnovationModel.innovation_id.asc())
        )
        return list(await self.session.scalars(statement))

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
