"""证据入湖和去重用例。"""

from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.evidence.normalization import normalize_evidence_source
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import EvidenceModel
from app.schemas.evidence import Evidence, EvidenceIngest, EvidenceIngestResult


class EvidenceService:
    """只执行确定性规范化、校验和持久化，不进行 LLM 推理。"""

    def __init__(self, repository: EvidenceRepository) -> None:
        self.repository = repository

    async def ingest(self, project_id: str, payload: EvidenceIngest) -> EvidenceIngestResult:
        if not await self.repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )

        normalized = normalize_evidence_source(
            str(payload.source_url), payload.original_excerpt
        )
        existing = await self.repository.get_evidence_by_hash(
            project_id, normalized.content_hash
        )
        if existing is not None:
            return EvidenceIngestResult(evidence=self._to_evidence(existing), created=False)

        model = EvidenceModel(
            evidence_id=f"ev_{uuid4().hex[:16]}",
            project_id=project_id,
            collection_job_id=payload.collection_job_id,
            source_url=str(payload.source_url),
            normalized_source_url=normalized.source_url,
            source_domain=normalized.source_domain,
            source_type=payload.source_type,
            title=payload.title,
            original_excerpt=payload.original_excerpt,
            claim_type=payload.claim_type,
            product=payload.product,
            region=payload.region,
            user_segment=payload.user_segment,
            published_at=payload.published_at,
            collected_at=payload.collected_at,
            status=payload.status,
            content_hash=normalized.content_hash,
            confidence=payload.confidence,
            authority_score=payload.authority_score,
            recency_score=payload.recency_score,
            diversity_score=payload.diversity_score,
        )
        try:
            await self.repository.add_evidence(model)
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            duplicate = await self.repository.get_evidence_by_hash(
                project_id, normalized.content_hash
            )
            if duplicate is None:
                raise
            return EvidenceIngestResult(evidence=self._to_evidence(duplicate), created=False)
        except Exception:
            await self.repository.rollback()
            raise

        return EvidenceIngestResult(evidence=self._to_evidence(model), created=True)

    @staticmethod
    def _to_evidence(model: EvidenceModel) -> Evidence:
        return Evidence.model_validate(
            {
                "evidence_id": model.evidence_id,
                "source_url": model.source_url,
                "source_domain": model.source_domain,
                "source_type": model.source_type,
                "title": model.title,
                "original_excerpt": model.original_excerpt,
                "claim_type": model.claim_type,
                "product": model.product,
                "region": model.region,
                "user_segment": model.user_segment,
                "published_at": model.published_at,
                "collected_at": model.collected_at,
                "status": model.status,
                "content_hash": model.content_hash,
                "confidence": model.confidence,
                "authority_score": model.authority_score,
                "recency_score": model.recency_score,
                "diversity_score": model.diversity_score,
            }
        )
