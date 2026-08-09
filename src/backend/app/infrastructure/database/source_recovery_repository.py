"""资料恢复记录的项目隔离查询与持久化。"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    CollectionJobModel,
    ProjectModel,
    SourceAssetModel,
    SourceRecoveryModel,
    SourceRecoverySubmissionModel,
)


class SourceRecoveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def get_source_asset(
        self, project_id: str, source_asset_id: str
    ) -> SourceAssetModel | None:
        statement = select(SourceAssetModel).where(
            SourceAssetModel.project_id == project_id,
            SourceAssetModel.source_asset_id == source_asset_id,
            SourceAssetModel.status == "ready",
        )
        return cast(SourceAssetModel | None, await self.session.scalar(statement))

    async def get_collection_job(
        self, project_id: str, collection_job_id: str
    ) -> CollectionJobModel | None:
        statement = select(CollectionJobModel).where(
            CollectionJobModel.project_id == project_id,
            CollectionJobModel.collection_job_id == collection_job_id,
        )
        return cast(CollectionJobModel | None, await self.session.scalar(statement))

    async def get(
        self, project_id: str, source_recovery_id: str
    ) -> SourceRecoveryModel | None:
        statement = (
            select(SourceRecoveryModel)
            .options(selectinload(SourceRecoveryModel.submissions))
            .where(
                SourceRecoveryModel.project_id == project_id,
                SourceRecoveryModel.source_recovery_id == source_recovery_id,
            )
        )
        return cast(SourceRecoveryModel | None, await self.session.scalar(statement))

    async def list(self, project_id: str) -> list[SourceRecoveryModel]:
        statement = (
            select(SourceRecoveryModel)
            .options(selectinload(SourceRecoveryModel.submissions))
            .where(SourceRecoveryModel.project_id == project_id)
            .order_by(SourceRecoveryModel.created_at.desc())
        )
        return list(await self.session.scalars(statement))

    async def find_open_for_source(
        self, project_id: str, source_asset_id: str
    ) -> SourceRecoveryModel | None:
        statement = (
            select(SourceRecoveryModel)
            .options(selectinload(SourceRecoveryModel.submissions))
            .where(
                SourceRecoveryModel.project_id == project_id,
                SourceRecoveryModel.failed_source_asset_id == source_asset_id,
                SourceRecoveryModel.status.in_(
                    ("waiting_for_user_input", "needs_more_information")
                ),
            )
            .order_by(SourceRecoveryModel.created_at.desc())
        )
        return cast(SourceRecoveryModel | None, await self.session.scalar(statement))

    async def get_submission_by_request(
        self, source_recovery_id: str, request_id: str
    ) -> SourceRecoverySubmissionModel | None:
        statement = select(SourceRecoverySubmissionModel).where(
            SourceRecoverySubmissionModel.source_recovery_id == source_recovery_id,
            SourceRecoverySubmissionModel.request_id == request_id,
        )
        return cast(SourceRecoverySubmissionModel | None, await self.session.scalar(statement))

    async def add_recovery(self, model: SourceRecoveryModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def add_submission(self, model: SourceRecoverySubmissionModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
