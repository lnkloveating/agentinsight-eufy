"""Fragment Evidence Draft、Gate 与晋级结果仓储。"""

from typing import cast

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    CollectionJobModel,
    CompetitorMaterialSelectionModel,
    CompetitorSourceOnboardingItemModel,
    EvidenceModel,
    FragmentEvidenceBatchItemModel,
    FragmentEvidenceBatchModel,
    ProjectModel,
    SourceAssetModel,
    SourceFragmentModel,
    SourceRoutingModel,
)


class FragmentEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def list_assets(
        self, project_id: str, source_asset_ids: list[str]
    ) -> list[SourceAssetModel]:
        statement = select(SourceAssetModel).where(
            SourceAssetModel.project_id == project_id,
            SourceAssetModel.source_asset_id.in_(source_asset_ids),
        )
        return list(await self.session.scalars(statement))

    async def list_fragments(
        self, project_id: str, source_asset_ids: list[str]
    ) -> list[SourceFragmentModel]:
        statement = (
            select(SourceFragmentModel)
            .where(
                SourceFragmentModel.project_id == project_id,
                SourceFragmentModel.source_asset_id.in_(source_asset_ids),
            )
            .order_by(SourceFragmentModel.source_asset_id, SourceFragmentModel.ordinal)
        )
        return list(await self.session.scalars(statement))

    async def list_collection_jobs(
        self, project_id: str, collection_job_ids: list[str]
    ) -> list[CollectionJobModel]:
        statement = select(CollectionJobModel).where(
            CollectionJobModel.project_id == project_id,
            CollectionJobModel.collection_job_id.in_(collection_job_ids),
        )
        return list(await self.session.scalars(statement))

    async def list_routings(
        self, project_id: str, source_asset_ids: list[str]
    ) -> list[SourceRoutingModel]:
        statement = select(SourceRoutingModel).where(
            SourceRoutingModel.project_id == project_id,
            SourceRoutingModel.source_asset_id.in_(source_asset_ids),
        )
        return list(await self.session.scalars(statement))

    async def list_material_lineage(
        self, project_id: str, source_asset_ids: list[str]
    ) -> list[CompetitorMaterialSelectionModel]:
        statement = select(CompetitorMaterialSelectionModel).where(
            CompetitorMaterialSelectionModel.project_id == project_id,
            CompetitorMaterialSelectionModel.source_asset_id.in_(source_asset_ids),
        )
        return list(await self.session.scalars(statement))

    async def list_onboarding_lineage(
        self, project_id: str, source_asset_ids: list[str]
    ) -> list[CompetitorSourceOnboardingItemModel]:
        statement = select(CompetitorSourceOnboardingItemModel).where(
            CompetitorSourceOnboardingItemModel.project_id == project_id,
            CompetitorSourceOnboardingItemModel.source_asset_id.in_(source_asset_ids),
        )
        return list(await self.session.scalars(statement))

    async def list_evidence_for_fragments(
        self, project_id: str, fragment_ids: list[str]
    ) -> list[EvidenceModel]:
        if not fragment_ids:
            return []
        statement = select(EvidenceModel).where(
            EvidenceModel.project_id == project_id,
            EvidenceModel.source_fragment_id.in_(fragment_ids),
        )
        return list(await self.session.scalars(statement))

    async def evidence_domain_counts(self, project_id: str) -> dict[str, int]:
        statement = (
            select(EvidenceModel.source_domain, func.count(EvidenceModel.evidence_id))
            .where(
                EvidenceModel.project_id == project_id,
                EvidenceModel.source_domain.is_not(None),
            )
            .group_by(EvidenceModel.source_domain)
        )
        rows = await self.session.execute(statement)
        return {str(domain): int(count) for domain, count in rows if domain is not None}

    @staticmethod
    def _loaded(
        statement: Select[tuple[FragmentEvidenceBatchModel]],
    ) -> Select[tuple[FragmentEvidenceBatchModel]]:
        return statement.options(
            selectinload(FragmentEvidenceBatchModel.items).selectinload(
                FragmentEvidenceBatchItemModel.source_fragment
            ),
            selectinload(FragmentEvidenceBatchModel.items).selectinload(
                FragmentEvidenceBatchItemModel.evidence
            ),
        )

    async def get_batch(
        self, project_id: str, batch_id: str
    ) -> FragmentEvidenceBatchModel | None:
        statement = select(FragmentEvidenceBatchModel).where(
            FragmentEvidenceBatchModel.project_id == project_id,
            FragmentEvidenceBatchModel.fragment_evidence_batch_id == batch_id,
        )
        return cast(
            FragmentEvidenceBatchModel | None,
            await self.session.scalar(self._loaded(statement)),
        )

    async def list_batches(self, project_id: str) -> list[FragmentEvidenceBatchModel]:
        statement = (
            select(FragmentEvidenceBatchModel)
            .where(FragmentEvidenceBatchModel.project_id == project_id)
            .order_by(
                FragmentEvidenceBatchModel.created_at.desc(),
                FragmentEvidenceBatchModel.fragment_evidence_batch_id.desc(),
            )
        )
        return list(await self.session.scalars(self._loaded(statement)))

    async def add(self, model: object) -> None:
        self.session.add(model)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
