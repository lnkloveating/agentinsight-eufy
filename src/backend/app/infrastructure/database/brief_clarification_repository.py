"""Persistence for pre-project Research Brief clarification sessions."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import BriefClarificationSessionModel


class BriefClarificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, model: BriefClarificationSessionModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def get(self, session_id: str) -> BriefClarificationSessionModel | None:
        return await self.session.get(BriefClarificationSessionModel, session_id)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
