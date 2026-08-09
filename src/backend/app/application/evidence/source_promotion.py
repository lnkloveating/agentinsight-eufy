from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.evidence.normalization import build_content_hash, normalize_url
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import EvidenceModel, ProjectEventModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.schemas.evidence import (
    Evidence,
    EvidenceFromSourceFragmentIngest,
    EvidenceIngestResult,
    EvidenceStatus,
)
from app.schemas.source import SourceAssetKind, SourceAssetStatus
from app.schemas.source_processing import (
    CollectionJobStatus,
    SourceFragmentVerificationStatus,
    SourceLocator,
    SourceLocatorKind,
)


class SourceEvidencePromotionService:
    """Promotes only a persisted, source-verified fragment into the Evidence Lake."""

    def __init__(
        self,
        source_repository: SourceAssetRepository,
        evidence_repository: EvidenceRepository,
        project_repository: ProjectRepository,
        trace_id: str,
        event_broker: ProjectEventBroker,
    ) -> None:
        self.source_repository = source_repository
        self.evidence_repository = evidence_repository
        self.project_repository = project_repository
        self.trace_id = trace_id
        self.event_broker = event_broker

    async def promote(
        self,
        project_id: str,
        payload: EvidenceFromSourceFragmentIngest,
        *,
        expected_source_asset_id: str | None = None,
    ) -> EvidenceIngestResult:
        if not await self.source_repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )
        fragment = await self.source_repository.get_fragment(project_id, payload.source_fragment_id)
        if fragment is None:
            raise AppError(
                code="SOURCE_FRAGMENT_NOT_FOUND",
                message="资料片段不存在。",
                status_code=404,
                details={"source_fragment_id": payload.source_fragment_id},
            )
        if (
            expected_source_asset_id is not None
            and fragment.source_asset_id != expected_source_asset_id
        ):
            raise AppError(
                code="SOURCE_FRAGMENT_ASSET_MISMATCH",
                message="资料片段不属于 URL 中指定的资料资产。",
                status_code=409,
                details={
                    "source_fragment_id": payload.source_fragment_id,
                    "expected_source_asset_id": expected_source_asset_id,
                },
            )
        if fragment.verification_status != SourceFragmentVerificationStatus.VERIFIED:
            raise AppError(
                code="SOURCE_FRAGMENT_NOT_VERIFIED",
                message="未经确定性校验的资料片段不能进入 Evidence Lake。",
                status_code=409,
            )
        asset = await self.source_repository.get_by_project(project_id, fragment.source_asset_id)
        artifact = await self.source_repository.get_parsed_artifact_by_id(
            project_id, fragment.parsed_artifact_id
        )
        if asset is None or artifact is None:
            raise AppError(
                code="SOURCE_PROVENANCE_INCOMPLETE",
                message="资料片段的原始来源链不完整。",
                status_code=409,
            )
        job = await self.source_repository.get_collection_job(artifact.collection_job_id)
        excerpt_hash = sha256(fragment.original_excerpt.encode("utf-8")).hexdigest()
        provenance_hash_matches = artifact.source_content_hash == asset.content_hash
        if asset.kind == SourceAssetKind.LINK:
            provenance_hash_matches = (
                job is not None
                and artifact.source_content_hash == job.result_json.get("captured_content_hash")
                and asset.storage_key is not None
            )
        locator = SourceLocator.model_validate(fragment.locator_json)
        media_locator_matches = True
        if locator.kind in {
            SourceLocatorKind.MEDIA_TIME,
            SourceLocatorKind.MEDIA_FRAME,
        }:
            manifest = job.result_json.get("media_manifest") if job is not None else None
            artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
            media_locator_matches = isinstance(artifacts, list) and any(
                isinstance(candidate, dict)
                and candidate.get("artifact_id") == locator.media_artifact_id
                and candidate.get("content_hash") == locator.media_artifact_hash
                for candidate in artifacts
            )
        if (
            asset.status != SourceAssetStatus.READY
            or artifact.source_asset_id != asset.source_asset_id
            or not provenance_hash_matches
            or not media_locator_matches
            or fragment.excerpt_hash != excerpt_hash
            or job is None
            or job.status != CollectionJobStatus.SUCCEEDED
        ):
            raise AppError(
                code="SOURCE_PROVENANCE_INVALID",
                message="资料片段未通过完整的来源链校验。",
                status_code=409,
            )

        content_hash = build_content_hash(fragment.original_excerpt)
        existing = await self.evidence_repository.get_evidence_by_hash(project_id, content_hash)
        if existing is not None:
            if not self._metadata_matches(existing, payload):
                raise AppError(
                    code="EVIDENCE_CONTENT_METADATA_CONFLICT",
                    message="相同原文已经使用不同的证据元数据进入 Evidence Lake。",
                    status_code=409,
                    details={"evidence_id": existing.evidence_id},
                )
            return EvidenceIngestResult(evidence=self._to_evidence(existing), created=False)

        source_url: str | None = asset.source_url
        if asset.kind == SourceAssetKind.LINK and job is not None:
            final_url = job.result_json.get("final_url")
            if isinstance(final_url, str):
                source_url = final_url
        normalized_source_url: str | None = None
        source_domain: str | None = None
        if source_url is not None:
            normalized_source_url, source_domain = normalize_url(source_url)
        now = datetime.now(UTC)
        model = EvidenceModel(
            evidence_id=f"ev_{uuid4().hex[:16]}",
            project_id=project_id,
            collection_job_id=artifact.collection_job_id,
            source_url=source_url,
            normalized_source_url=normalized_source_url,
            source_domain=source_domain,
            source_asset_id=asset.source_asset_id,
            source_fragment_id=fragment.source_fragment_id,
            source_locator_json=fragment.locator_json,
            source_type=asset.media_category,
            title=asset.display_name,
            original_excerpt=fragment.original_excerpt,
            claim_type=payload.claim_type,
            product=payload.product,
            region=payload.region,
            user_segment=payload.user_segment,
            published_at=payload.published_at,
            collected_at=now,
            # Provenance is verified, but one excerpt alone does not establish factual truth.
            status=EvidenceStatus.PARTIALLY_VERIFIED,
            content_hash=content_hash,
            confidence=payload.confidence,
            authority_score=payload.authority_score,
            recency_score=payload.recency_score,
            diversity_score=payload.diversity_score,
        )
        try:
            await self.evidence_repository.add_evidence(model)
            await self.project_repository.add_event(
                ProjectEventModel(
                    event_id=f"evt_{uuid4().hex[:16]}",
                    project_id=project_id,
                    sequence_number=0,
                    event_type="source_fragment_promoted",
                    data_json={
                        "source_asset_id": asset.source_asset_id,
                        "source_fragment_id": fragment.source_fragment_id,
                        "evidence_id": model.evidence_id,
                        "status": model.status,
                    },
                    trace_id=self.trace_id,
                    created_at=now,
                )
            )
            await self.evidence_repository.commit()
        except IntegrityError:
            await self.evidence_repository.rollback()
            duplicate = await self.evidence_repository.get_evidence_by_hash(
                project_id, content_hash
            )
            if duplicate is None:
                raise
            return EvidenceIngestResult(evidence=self._to_evidence(duplicate), created=False)
        except Exception:
            await self.evidence_repository.rollback()
            raise
        await self.event_broker.notify(project_id)
        return EvidenceIngestResult(evidence=self._to_evidence(model), created=True)

    @staticmethod
    def _metadata_matches(
        model: EvidenceModel,
        payload: EvidenceFromSourceFragmentIngest,
    ) -> bool:
        def normalized_time(value: datetime | None) -> datetime | None:
            if value is None:
                return None
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)

        return (
            model.claim_type == payload.claim_type.value
            and model.product == payload.product
            and model.region == payload.region
            and model.user_segment == payload.user_segment
            and normalized_time(model.published_at) == normalized_time(payload.published_at)
            and model.confidence == payload.confidence
            and model.authority_score == payload.authority_score
            and model.recency_score == payload.recency_score
            and model.diversity_score == payload.diversity_score
        )

    @staticmethod
    def _to_evidence(model: EvidenceModel) -> Evidence:
        return Evidence.model_validate(
            {
                "evidence_id": model.evidence_id,
                "source_url": model.source_url,
                "source_domain": model.source_domain,
                "source_asset_id": model.source_asset_id,
                "source_fragment_id": model.source_fragment_id,
                "source_locator": model.source_locator_json,
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
