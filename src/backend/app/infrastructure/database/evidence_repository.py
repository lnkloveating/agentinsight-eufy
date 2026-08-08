"""Evidence Lake 的数据库仓储。"""

from typing import cast

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    ClaimEvidenceLinkModel,
    ClaimModel,
    CollectionJobModel,
    EvidenceModel,
    ProjectModel,
)


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def project_exists(self, project_id: str) -> bool:
        return await self.session.get(ProjectModel, project_id) is not None

    async def get_evidence(self, evidence_id: str) -> EvidenceModel | None:
        return await self.session.get(EvidenceModel, evidence_id)

    async def list_evidence(
        self,
        project_id: str,
        *,
        cursor: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
    ) -> tuple[list[EvidenceModel], str | None, int]:
        filters = [EvidenceModel.project_id == project_id]
        if status is not None:
            filters.append(EvidenceModel.status == status)
        if source_type is not None:
            filters.append(EvidenceModel.source_type == source_type)

        total_statement = select(func.count(EvidenceModel.evidence_id)).where(*filters)
        total = int(await self.session.scalar(total_statement) or 0)

        page_filters = list(filters)
        if cursor is not None:
            page_filters.append(EvidenceModel.evidence_id > cursor)
        statement = (
            select(EvidenceModel)
            .where(*page_filters)
            .order_by(EvidenceModel.evidence_id.asc())
            .limit(limit + 1)
        )
        models = list(await self.session.scalars(statement))
        has_more = len(models) > limit
        items = models[:limit]
        next_cursor = items[-1].evidence_id if has_more and items else None
        return items, next_cursor, total

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

    async def get_evidence_by_ids(self, evidence_ids: set[str]) -> list[EvidenceModel]:
        if not evidence_ids:
            return []
        statement = select(EvidenceModel).where(EvidenceModel.evidence_id.in_(evidence_ids))
        result = await self.session.scalars(statement)
        return list(result)

    async def list_eligible_agent_evidence(
        self,
        project_id: str,
        *,
        statuses: set[str],
        claim_types: set[str] | None = None,
        limit: int,
    ) -> tuple[list[EvidenceModel], int]:
        """Return bounded, project-scoped evidence ranked without LLM reasoning."""

        filters = [
            EvidenceModel.project_id == project_id,
            EvidenceModel.status.in_(statuses),
        ]
        if claim_types is not None:
            filters.append(EvidenceModel.claim_type.in_(claim_types))
        total = int(
            await self.session.scalar(select(func.count(EvidenceModel.evidence_id)).where(*filters))
            or 0
        )
        verified_first = case(
            (EvidenceModel.status == "verified", 0),
            else_=1,
        )
        quality = (
            EvidenceModel.confidence
            + EvidenceModel.authority_score
            + EvidenceModel.recency_score
            + EvidenceModel.diversity_score
        )
        models = list(
            await self.session.scalars(
                select(EvidenceModel)
                .where(*filters)
                .order_by(
                    verified_first.asc(),
                    quality.desc(),
                    EvidenceModel.evidence_id.asc(),
                )
                .limit(limit)
            )
        )
        return models, total

    async def add_claim(self, claim: ClaimModel) -> None:
        self.session.add(claim)
        await self.session.flush()

    async def add_claim_evidence_link(self, link: ClaimEvidenceLinkModel) -> None:
        self.session.add(link)
        await self.session.flush()

    async def list_claims(
        self, project_id: str
    ) -> tuple[list[ClaimModel], list[ClaimEvidenceLinkModel]]:
        claims = list(
            await self.session.scalars(
                select(ClaimModel)
                .where(ClaimModel.project_id == project_id)
                .order_by(ClaimModel.claim_id.asc())
            )
        )
        if not claims:
            return [], []
        claim_ids = [claim.claim_id for claim in claims]
        links = list(
            await self.session.scalars(
                select(ClaimEvidenceLinkModel)
                .where(ClaimEvidenceLinkModel.claim_id.in_(claim_ids))
                .order_by(ClaimEvidenceLinkModel.created_at.asc())
            )
        )
        return claims, links

    async def add_collection_job(self, job: CollectionJobModel) -> None:
        self.session.add(job)
        await self.session.flush()

    async def get_collection_job(self, collection_job_id: str) -> CollectionJobModel | None:
        return await self.session.get(CollectionJobModel, collection_job_id)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
