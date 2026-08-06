"""Evidence 与 Claim 的只读查询用例。"""

from collections import defaultdict

from app.core.errors import AppError
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.schemas.evidence import (
    Claim,
    Evidence,
    EvidencePage,
    EvidenceRelationship,
    EvidenceStatus,
)


class EvidenceQueryService:
    def __init__(self, repository: EvidenceRepository) -> None:
        self.repository = repository

    async def list_evidence(
        self,
        project_id: str,
        *,
        cursor: str | None = None,
        status: EvidenceStatus | None = None,
        source_type: str | None = None,
        limit: int = 50,
    ) -> EvidencePage:
        await self._require_project(project_id)
        models, next_cursor, total = await self.repository.list_evidence(
            project_id,
            cursor=cursor,
            status=status.value if status is not None else None,
            source_type=source_type,
            limit=limit,
        )
        return EvidencePage(
            items=[EvidenceServiceMapper.to_evidence(model) for model in models],
            next_cursor=next_cursor,
            total=total,
        )

    async def list_claims(self, project_id: str) -> list[Claim]:
        await self._require_project(project_id)
        models, links = await self.repository.list_claims(project_id)
        supporting: defaultdict[str, list[str]] = defaultdict(list)
        contradicting: defaultdict[str, list[str]] = defaultdict(list)
        for link in links:
            if link.relation_type == EvidenceRelationship.SUPPORTS:
                supporting[link.claim_id].append(link.evidence_id)
            elif link.relation_type == EvidenceRelationship.CONTRADICTS:
                contradicting[link.claim_id].append(link.evidence_id)

        return [
            Claim.model_validate(
                {
                    "claim_id": model.claim_id,
                    "statement": model.statement,
                    "claim_type": model.claim_type,
                    "evidence_ids": supporting[model.claim_id],
                    "contradicting_evidence_ids": contradicting[model.claim_id],
                    "scope": model.scope_json,
                    "status": model.status,
                }
            )
            for model in models
        ]

    async def _require_project(self, project_id: str) -> None:
        if not await self.repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )


class EvidenceServiceMapper:
    """集中保存数据库模型到公开 Schema 的确定性映射。"""

    @staticmethod
    def to_evidence(model: object) -> Evidence:
        return Evidence.model_validate(model, from_attributes=True)
