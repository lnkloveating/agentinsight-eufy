"""Evidence Lake 的数据库仓储。"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import EvidenceModel, ProjectModel


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def project_exists(self, project_id: str) -> bool:
        return await self.session.get(ProjectModel, project_id) is not None

    async def get_evidence(self, evidence_id: str) -> EvidenceModel | None:
        return await self.session.get(EvidenceModel, evidence_id)

    async def get_evidence_by_hash(
        self, project_id: str, content_hash: str
    ) -> EvidenceModel | None:
        statement = select(EvidenceModel).where(
            EvidenceModel.project_id == project_id,
            EvidenceModel.content_hash == content_hash,
        )
        return cast(EvidenceModel | None, await self.session.scalar(statement))

    async def add_evidence(self, evidence: EvidenceModel) -> None:
        self.session.add(evidence)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
