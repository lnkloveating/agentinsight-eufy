from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.models import (
    CollectionJobModel,
    ParsedArtifactModel,
    ProjectEventModel,
    SourceAssetModel,
    SourceFragmentModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.infrastructure.source_processing_workspace import (
    SourceProcessingWorkspaceManager,
)
from app.infrastructure.source_storage import LocalSourceStorage
from app.schemas.source import SourceAssetKind, SourceAssetStatus, SourceMediaCategory
from app.schemas.source_processing import (
    CollectionJobStatus,
    MediaFragmentReview,
    MediaFragmentReviewDecision,
    ParsedArtifact,
    SourceFragment,
    SourceFragmentPage,
    SourceFragmentVerificationStatus,
    SourceLocator,
    SourceLocatorKind,
    SourceProcessingJob,
    SourceProcessingStatus,
)
from app.sources.media_processing import (
    MediaProcessingError,
    MediaUnderstandingConnector,
    PyAvMediaProcessor,
    validate_media_understanding,
)
from app.sources.parsers import (
    DeterministicParseResult,
    ParsedFragmentCandidate,
    SourceParserError,
    SourceParserRegistry,
)
from app.sources.web_connector import WebConnector, WebConnectorError


class SourceProcessingService:
    """Runs bounded deterministic parsing and persists only source-verified excerpts."""

    def __init__(
        self,
        repository: SourceAssetRepository,
        project_repository: ProjectRepository,
        storage: LocalSourceStorage,
        workspaces: SourceProcessingWorkspaceManager,
        parsers: SourceParserRegistry,
        *,
        web_connector: WebConnector | None,
        media_processor: PyAvMediaProcessor,
        media_understanding_connector: MediaUnderstandingConnector | None,
        max_input_bytes: int,
        max_fragments: int,
        trace_id: str,
        event_broker: ProjectEventBroker,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.storage = storage
        self.workspaces = workspaces
        self.parsers = parsers
        self.web_connector = web_connector
        self.media_processor = media_processor
        self.media_understanding_connector = media_understanding_connector
        self.max_input_bytes = max_input_bytes
        self.max_fragments = max_fragments
        self.trace_id = trace_id
        self.event_broker = event_broker

    async def get_status(
        self, project_id: str, source_asset_id: str
    ) -> SourceProcessingStatus:
        asset, job = await self._require_asset_and_job(project_id, source_asset_id)
        artifact = await self.repository.get_parsed_artifact(
            project_id, source_asset_id, job.collection_job_id
        )
        return self._to_status(asset, job, artifact)

    async def process(
        self, project_id: str, source_asset_id: str
    ) -> SourceProcessingStatus:
        asset, job = await self._require_asset_and_job(project_id, source_asset_id)
        if job.status == CollectionJobStatus.SUCCEEDED:
            return await self.get_status(project_id, source_asset_id)
        if job.status != CollectionJobStatus.QUEUED:
            raise AppError(
                code="SOURCE_PROCESSING_STATE_CONFLICT",
                message="当前资料处理任务不是可执行的排队状态。",
                status_code=409,
                details={"status": job.status},
            )
        if asset.status == SourceAssetStatus.DELETED:
            return await self._finish_error(
                asset,
                job,
                code="SOURCE_ASSET_DELETED",
                message="原始资料已删除，不能继续处理。",
                blocked=True,
            )

        now = datetime.now(UTC)
        job.status = CollectionJobStatus.RUNNING
        job.attempt_count += 1
        job.result_json = {"source_asset_id": source_asset_id, "progress": 10}
        job.error_code = None
        job.error_message = None
        job.started_at = now
        job.completed_at = None
        job.updated_at = now
        await self._add_event(asset, job, "source_processing_started", now)
        await self.repository.commit()
        await self.event_broker.notify(project_id)

        collection_job_id = job.collection_job_id
        workspace: Path | None = None
        captured_storage_key: str | None = None
        web_result: dict[str, object] = {}
        try:
            if asset.kind == SourceAssetKind.LINK:
                if self.web_connector is None:
                    raise SourceParserError(
                        "SOURCE_CONNECTOR_NOT_CONFIGURED",
                        "Registered links require an explicit web connector before processing.",
                        blocked=True,
                    )
                if asset.source_url is None:
                    raise SourceParserError(
                        "SOURCE_URL_MISSING",
                        "The registered webpage source URL is missing.",
                        blocked=True,
                    )
                fetched = await self.web_connector.fetch(asset.source_url)
                if len(fetched.body_utf8) > self.max_input_bytes:
                    raise SourceParserError(
                        "SOURCE_PROCESSING_INPUT_TOO_LARGE",
                        "The captured webpage exceeds the deterministic processing size limit.",
                        blocked=True,
                    )
                materialized = self.workspaces.materialize_bytes(
                    project_id=project_id,
                    collection_job_id=collection_job_id,
                    content=fetched.body_utf8,
                    suffix=".html",
                )
                web_result = {
                    "captured_content_hash": materialized.content_hash,
                    "requested_url": fetched.requested_url,
                    "final_url": fetched.final_url,
                    "http_status": fetched.status_code,
                    "fetched_at": fetched.fetched_at.isoformat(),
                    "etag": fetched.etag,
                    "last_modified": fetched.last_modified,
                }
            else:
                if asset.byte_size > self.max_input_bytes:
                    raise SourceParserError(
                        "SOURCE_PROCESSING_INPUT_TOO_LARGE",
                        "The source exceeds the deterministic processing size limit.",
                        blocked=True,
                    )
                source_path = self.storage.resolve_for_read(asset.storage_key)
                materialized = self.workspaces.materialize(
                    project_id=project_id,
                    collection_job_id=collection_job_id,
                    source_path=source_path,
                )
                if materialized.content_hash != asset.content_hash:
                    raise SourceParserError(
                        "SOURCE_CONTENT_HASH_MISMATCH",
                        "The stored source no longer matches its registered content hash.",
                    )
            workspace = materialized.workspace
            verification_status = SourceFragmentVerificationStatus.VERIFIED
            processing_result = dict(web_result)
            if asset.media_category in {
                SourceMediaCategory.AUDIO,
                SourceMediaCategory.VIDEO,
            }:
                parsed, media_result = await self._parse_media(
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    source_path=materialized.source_path,
                    output_directory=materialized.workspace / "media",
                )
                verification_status = SourceFragmentVerificationStatus.DERIVED
                processing_result.update(media_result)
            else:
                parser = self.parsers.get(asset.media_type)
                parsed = parser.parse(materialized.source_path)
                # This is a second read of the isolated source snapshot. No LLM output
                # can satisfy this check without matching the source bytes or page.
                parser.verify(materialized.source_path, parsed.fragments)
            if not parsed.fragments:
                raise SourceParserError(
                    "SOURCE_NO_EXTRACTABLE_CONTENT",
                    "The source does not contain extractable text.",
                    blocked=True,
                )
            if len(parsed.fragments) > self.max_fragments:
                raise SourceParserError(
                    "SOURCE_FRAGMENT_LIMIT_EXCEEDED",
                    "The source produced more fragments than the configured safe limit.",
                    blocked=True,
                )
            if asset.kind == SourceAssetKind.LINK:
                stored_snapshot = self.storage.save_bytes(
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    suffix=".html",
                    content=materialized.source_path.read_bytes(),
                )
                if stored_snapshot.content_hash != materialized.content_hash:
                    raise SourceParserError(
                        "SOURCE_CONTENT_HASH_MISMATCH",
                        "The persisted webpage snapshot did not match the verified capture.",
                    )
                captured_storage_key = stored_snapshot.storage_key
                asset.storage_key = stored_snapshot.storage_key
                asset.byte_size = stored_snapshot.byte_size
                asset.media_type = "text/html"
                asset.updated_at = datetime.now(UTC)

            completed_at = datetime.now(UTC)
            artifact = ParsedArtifactModel(
                parsed_artifact_id=f"parsed_{uuid4().hex[:16]}",
                project_id=project_id,
                source_asset_id=source_asset_id,
                collection_job_id=collection_job_id,
                parser_id=parsed.parser_id,
                parser_version=parsed.parser_version,
                source_content_hash=materialized.content_hash,
                fragment_count=len(parsed.fragments),
                created_at=completed_at,
            )
            fragments = [
                SourceFragmentModel(
                    source_fragment_id=f"fragment_{uuid4().hex[:16]}",
                    parsed_artifact_id=artifact.parsed_artifact_id,
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    ordinal=ordinal,
                    locator_json=candidate.locator.model_dump(mode="json"),
                    original_excerpt=candidate.original_excerpt,
                    excerpt_hash=sha256(
                        candidate.original_excerpt.encode("utf-8")
                    ).hexdigest(),
                    verification_status=verification_status,
                    created_at=completed_at,
                )
                for ordinal, candidate in enumerate(parsed.fragments)
            ]
            await self.repository.add_parsed_artifact(artifact)
            await self.repository.add_source_fragments(fragments)
            job.status = CollectionJobStatus.SUCCEEDED
            job.result_json = {
                "source_asset_id": source_asset_id,
                "parsed_artifact_id": artifact.parsed_artifact_id,
                "fragment_count": len(fragments),
                "progress": 100,
                "verification": (
                    "human_review_required"
                    if verification_status
                    is SourceFragmentVerificationStatus.DERIVED
                    else "deterministic"
                ),
                **processing_result,
            }
            job.completed_at = completed_at
            job.updated_at = completed_at
            await self._add_event(
                asset, job, "source_processing_succeeded", completed_at
            )
            await self.repository.commit()
            await self.event_broker.notify(project_id)
            return self._to_status(asset, job, artifact)
        except MediaProcessingError as exc:
            await self.repository.rollback()
            self.storage.delete(captured_storage_key)
            current_asset = await self.repository.get_by_project(
                project_id, source_asset_id
            )
            current_job = await self.repository.get_collection_job(collection_job_id)
            if current_asset is None or current_job is None:
                raise
            return await self._finish_error(
                current_asset,
                current_job,
                code=exc.code,
                message=exc.message,
                blocked=exc.blocked,
                extra_result=exc.result,
            )
        except WebConnectorError as exc:
            await self.repository.rollback()
            self.storage.delete(captured_storage_key)
            current_asset = await self.repository.get_by_project(
                project_id, source_asset_id
            )
            current_job = await self.repository.get_collection_job(collection_job_id)
            if current_asset is None or current_job is None:
                raise
            return await self._finish_error(
                current_asset,
                current_job,
                code=exc.code,
                message=exc.message,
                blocked=exc.blocked,
            )
        except SourceParserError as exc:
            await self.repository.rollback()
            self.storage.delete(captured_storage_key)
            current_asset = await self.repository.get_by_project(
                project_id, source_asset_id
            )
            current_job = await self.repository.get_collection_job(collection_job_id)
            if current_asset is None or current_job is None:
                raise
            return await self._finish_error(
                current_asset,
                current_job,
                code=exc.code,
                message=exc.message,
                blocked=exc.blocked,
            )
        except AppError as exc:
            await self.repository.rollback()
            self.storage.delete(captured_storage_key)
            current_asset = await self.repository.get_by_project(
                project_id, source_asset_id
            )
            current_job = await self.repository.get_collection_job(collection_job_id)
            if current_asset is None or current_job is None:
                raise
            return await self._finish_error(
                current_asset,
                current_job,
                code=exc.code,
                message=exc.message,
                blocked=exc.code == "SOURCE_CONTENT_MISSING",
            )
        except Exception:
            await self.repository.rollback()
            self.storage.delete(captured_storage_key)
            current_asset = await self.repository.get_by_project(
                project_id, source_asset_id
            )
            current_job = await self.repository.get_collection_job(collection_job_id)
            if current_asset is None or current_job is None:
                raise
            return await self._finish_error(
                current_asset,
                current_job,
                code="SOURCE_PROCESSING_FAILED",
                message="资料处理失败，未生成解析产物。",
                blocked=False,
            )
        finally:
            self.workspaces.cleanup(workspace)

    async def retry(
        self, project_id: str, source_asset_id: str
    ) -> SourceProcessingStatus:
        asset, job = await self._require_asset_and_job(project_id, source_asset_id)
        if job.status == CollectionJobStatus.SUCCEEDED:
            return await self.get_status(project_id, source_asset_id)
        if job.status == CollectionJobStatus.RUNNING:
            raise AppError(
                code="SOURCE_PROCESSING_STATE_CONFLICT",
                message="运行中的资料处理任务不能重试。",
                status_code=409,
                details={"status": job.status},
            )
        if job.status not in {
            CollectionJobStatus.FAILED,
            CollectionJobStatus.BLOCKED,
            CollectionJobStatus.CANCELLED,
        }:
            return await self.process(project_id, source_asset_id)
        if asset.status == SourceAssetStatus.DELETED:
            return await self.get_status(project_id, source_asset_id)
        now = datetime.now(UTC)
        job.status = CollectionJobStatus.QUEUED
        job.result_json = {"source_asset_id": source_asset_id, "progress": 0}
        job.error_code = None
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        job.updated_at = now
        await self.repository.commit()
        return await self.process(project_id, source_asset_id)

    async def cancel(
        self, project_id: str, source_asset_id: str
    ) -> SourceProcessingStatus:
        asset, job = await self._require_asset_and_job(project_id, source_asset_id)
        if job.status != CollectionJobStatus.QUEUED:
            if job.status == CollectionJobStatus.RUNNING:
                raise AppError(
                    code="SOURCE_PROCESSING_STATE_CONFLICT",
                    message="同步执行中的资料处理任务不能通过另一个请求取消。",
                    status_code=409,
                    details={"status": job.status},
                )
            return await self.get_status(project_id, source_asset_id)
        now = datetime.now(UTC)
        job.status = CollectionJobStatus.CANCELLED
        job.result_json = {"source_asset_id": source_asset_id, "progress": 100}
        job.error_code = "SOURCE_PROCESSING_CANCELLED"
        job.error_message = "资料处理任务已在执行前取消。"
        job.completed_at = now
        job.updated_at = now
        await self._add_event(asset, job, "source_processing_cancelled", now)
        await self.repository.commit()
        await self.event_broker.notify(project_id)
        return self._to_status(asset, job, None)

    async def list_fragments(
        self,
        project_id: str,
        source_asset_id: str,
        *,
        cursor: str | None,
    ) -> SourceFragmentPage:
        await self._require_asset_and_job(project_id, source_asset_id)
        try:
            after_ordinal = int(cursor) if cursor is not None else None
        except ValueError as exc:
            raise AppError(
                code="SOURCE_FRAGMENT_CURSOR_INVALID",
                message="资料片段游标无效。",
                status_code=422,
            ) from exc
        if after_ordinal is not None and after_ordinal < 0:
            raise AppError(
                code="SOURCE_FRAGMENT_CURSOR_INVALID",
                message="资料片段游标无效。",
                status_code=422,
            )
        models, next_cursor, total = await self.repository.list_fragments(
            project_id, source_asset_id, after_ordinal=after_ordinal
        )
        return SourceFragmentPage(
            items=[self._to_fragment(model) for model in models],
            next_cursor=next_cursor,
            total=total,
        )

    async def review_media_fragment(
        self,
        project_id: str,
        source_asset_id: str,
        source_fragment_id: str,
        payload: MediaFragmentReview,
    ) -> SourceFragment:
        asset, job = await self._require_asset_and_job(project_id, source_asset_id)
        if asset.media_category not in {
            SourceMediaCategory.AUDIO,
            SourceMediaCategory.VIDEO,
        }:
            raise AppError(
                code="MEDIA_FRAGMENT_REVIEW_NOT_APPLICABLE",
                message="Only media-derived fragments can be reviewed.",
                status_code=409,
            )
        fragment = await self.repository.get_fragment(project_id, source_fragment_id)
        if fragment is None or fragment.source_asset_id != source_asset_id:
            raise AppError(
                code="SOURCE_FRAGMENT_NOT_FOUND",
                message="The source fragment does not exist.",
                status_code=404,
            )
        if fragment.verification_status != SourceFragmentVerificationStatus.DERIVED:
            raise AppError(
                code="MEDIA_FRAGMENT_ALREADY_REVIEWED",
                message="The media-derived fragment has already been reviewed.",
                status_code=409,
            )
        locator = SourceLocator.model_validate(fragment.locator_json)
        if locator.media_artifact_id is None:
            raise AppError(
                code="SOURCE_PROVENANCE_INVALID",
                message="The media fragment does not reference a retained artifact.",
                status_code=409,
            )
        retained_path, _ = self._resolve_media_artifact(
            asset, job, locator.media_artifact_id
        )
        if locator.media_artifact_hash != sha256(retained_path.read_bytes()).hexdigest():
            raise AppError(
                code="MEDIA_ARTIFACT_HASH_MISMATCH",
                message="The reviewed media artifact does not match the fragment locator.",
                status_code=409,
            )
        fragment.verification_status = (
            SourceFragmentVerificationStatus.VERIFIED
            if payload.decision is MediaFragmentReviewDecision.VERIFIED
            else SourceFragmentVerificationStatus.INVALID
        )
        now = datetime.now(UTC)
        await self.project_repository.add_event(
            ProjectEventModel(
                event_id=f"evt_{uuid4().hex[:16]}",
                project_id=project_id,
                sequence_number=0,
                event_type="media_fragment_reviewed",
                data_json={
                    "source_asset_id": source_asset_id,
                    "source_fragment_id": source_fragment_id,
                    "decision": payload.decision,
                    "reviewer": payload.reviewer,
                    "reason": payload.reason,
                },
                trace_id=self.trace_id,
                created_at=now,
            )
        )
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(project_id)
        return self._to_fragment(fragment)

    async def get_media_artifact(
        self, project_id: str, source_asset_id: str, media_artifact_id: str
    ) -> tuple[Path, str]:
        asset, job = await self._require_asset_and_job(project_id, source_asset_id)
        return self._resolve_media_artifact(asset, job, media_artifact_id)

    async def _finish_error(
        self,
        asset: SourceAssetModel,
        job: CollectionJobModel,
        *,
        code: str,
        message: str,
        blocked: bool,
        extra_result: dict[str, object] | None = None,
    ) -> SourceProcessingStatus:
        now = datetime.now(UTC)
        job.status = (
            CollectionJobStatus.BLOCKED if blocked else CollectionJobStatus.FAILED
        )
        job.result_json = {
            "source_asset_id": asset.source_asset_id,
            "progress": 100,
            "coverage_gap": True,
            **(extra_result or {}),
        }
        job.error_code = code
        job.error_message = message
        job.completed_at = now
        job.updated_at = now
        await self._add_event(
            asset,
            job,
            "source_processing_blocked" if blocked else "source_processing_failed",
            now,
        )
        await self.repository.commit()
        await self.event_broker.notify(asset.project_id)
        return self._to_status(asset, job, None)

    async def _parse_media(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        source_path: Path,
        output_directory: Path,
    ) -> tuple[DeterministicParseResult, dict[str, object]]:
        self.storage.delete_derived(project_id, source_asset_id)
        prepared = self.media_processor.prepare(source_path, output_directory)
        try:
            for media_artifact in prepared.artifacts:
                suffix = (
                    ".wav" if media_artifact.media_type == "audio/wav" else ".png"
                )
                stored = self.storage.save_derived_bytes(
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    artifact_id=media_artifact.artifact_id,
                    suffix=suffix,
                    content=media_artifact.path.read_bytes(),
                )
                if (
                    stored.content_hash != media_artifact.content_hash
                    or stored.byte_size != media_artifact.byte_size
                ):
                    raise MediaProcessingError(
                        "MEDIA_ARTIFACT_HASH_MISMATCH",
                        "A retained media artifact did not match the decoded output.",
                    )
        except Exception:
            self.storage.delete_derived(project_id, source_asset_id)
            raise
        media_result: dict[str, object] = {
            "media_manifest": prepared.public_manifest(),
            "semantic_analysis": "pending",
        }
        connector = self.media_understanding_connector
        if connector is None:
            raise MediaProcessingError(
                "MEDIA_UNDERSTANDING_CONNECTOR_NOT_CONFIGURED",
                "Media was decoded safely, but no ASR or vision connector is configured.",
                blocked=True,
                result=media_result,
            )
        try:
            understood = await connector.analyze(prepared)
        except MediaProcessingError:
            raise
        except Exception as exc:
            raise MediaProcessingError(
                "MEDIA_UNDERSTANDING_FAILED",
                "The media understanding connector failed without producing fragments.",
                result=media_result,
            ) from exc
        if (
            understood.connector_id != connector.connector_id
            or understood.connector_version != connector.connector_version
            or understood.model_id != connector.model_id
        ):
            raise MediaProcessingError(
                "MEDIA_UNDERSTANDING_INVALID",
                "The media connector returned inconsistent identity metadata.",
                result=media_result,
            )
        try:
            derived = validate_media_understanding(
                prepared,
                understood,
                max_fragments=self.max_fragments,
                max_text_chars=20_000,
            )
        except MediaProcessingError as exc:
            raise MediaProcessingError(
                exc.code,
                exc.message,
                blocked=exc.blocked,
                result=media_result,
            ) from exc
        candidates = tuple(
            ParsedFragmentCandidate(
                locator=SourceLocator(
                    kind=SourceLocatorKind(item.kind),
                    timestamp_start_ms=item.timestamp_start_ms,
                    timestamp_end_ms=item.timestamp_end_ms,
                    frame_index=item.media_artifact.frame_index,
                    media_artifact_id=item.media_artifact.artifact_id,
                    media_artifact_hash=item.media_artifact.content_hash,
                    connector_id=understood.connector_id,
                    model_id=understood.model_id,
                    confidence=item.confidence,
                ),
                original_excerpt=item.text,
            )
            for item in derived
        )
        media_result.update(
            {
                "semantic_analysis": "completed",
                "connector_id": understood.connector_id,
                "connector_version": understood.connector_version,
                "model_id": understood.model_id,
                "review_required": True,
            }
        )
        return (
            DeterministicParseResult(
                parser_id=f"media-{understood.connector_id}",
                parser_version=understood.connector_version,
                fragments=candidates,
            ),
            media_result,
        )

    def _resolve_media_artifact(
        self,
        asset: SourceAssetModel,
        job: CollectionJobModel,
        media_artifact_id: str,
    ) -> tuple[Path, str]:
        manifest = job.result_json.get("media_manifest")
        artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
        if not isinstance(artifacts, list):
            raise AppError(
                code="MEDIA_ARTIFACT_NOT_FOUND",
                message="No retained media artifacts exist for this source.",
                status_code=404,
            )
        metadata = next(
            (
                candidate
                for candidate in artifacts
                if isinstance(candidate, dict)
                and candidate.get("artifact_id") == media_artifact_id
            ),
            None,
        )
        if metadata is None:
            raise AppError(
                code="MEDIA_ARTIFACT_NOT_FOUND",
                message="The requested media artifact does not exist.",
                status_code=404,
            )
        media_type = metadata.get("media_type")
        if media_type not in {"audio/wav", "image/png"}:
            raise AppError(
                code="MEDIA_ARTIFACT_TYPE_INVALID",
                message="The retained media artifact type is invalid.",
                status_code=409,
            )
        suffix = ".wav" if media_type == "audio/wav" else ".png"
        path = self.storage.resolve_derived_for_read(
            project_id=asset.project_id,
            source_asset_id=asset.source_asset_id,
            artifact_id=media_artifact_id,
            suffix=suffix,
        )
        expected_hash = metadata.get("content_hash")
        actual_hash = sha256(path.read_bytes()).hexdigest()
        if expected_hash != actual_hash:
            raise AppError(
                code="MEDIA_ARTIFACT_HASH_MISMATCH",
                message="The retained media artifact failed its integrity check.",
                status_code=409,
            )
        return path, media_type

    async def _require_asset_and_job(
        self, project_id: str, source_asset_id: str
    ) -> tuple[SourceAssetModel, CollectionJobModel]:
        if not await self.repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )
        asset = await self.repository.get_by_project(project_id, source_asset_id)
        if asset is None:
            raise AppError(
                code="SOURCE_ASSET_NOT_FOUND",
                message="原始资料不存在。",
                status_code=404,
                details={"source_asset_id": source_asset_id},
            )
        job = await self.repository.get_collection_job(asset.collection_job_id)
        if job is None:
            raise AppError(
                code="COLLECTION_JOB_NOT_FOUND",
                message="资料处理任务不存在。",
                status_code=409,
                details={"collection_job_id": asset.collection_job_id},
            )
        return asset, job

    async def _add_event(
        self,
        asset: SourceAssetModel,
        job: CollectionJobModel,
        event_type: str,
        now: datetime,
    ) -> None:
        await self.project_repository.add_event(
            ProjectEventModel(
                event_id=f"evt_{uuid4().hex[:16]}",
                project_id=asset.project_id,
                sequence_number=0,
                event_type=event_type,
                data_json={
                    "source_asset_id": asset.source_asset_id,
                    "collection_job_id": job.collection_job_id,
                    "status": job.status,
                    "attempt_count": job.attempt_count,
                    "error_code": job.error_code,
                },
                trace_id=self.trace_id,
                created_at=now,
            )
        )

    @classmethod
    def _to_status(
        cls,
        asset: SourceAssetModel,
        job: CollectionJobModel,
        artifact: ParsedArtifactModel | None,
    ) -> SourceProcessingStatus:
        return SourceProcessingStatus(
            job=SourceProcessingJob(
                collection_job_id=job.collection_job_id,
                project_id=job.project_id,
                source_asset_id=asset.source_asset_id,
                source_type=job.source_type,
                status=CollectionJobStatus(job.status),
                attempt_count=job.attempt_count,
                progress=int(job.result_json.get("progress", 0)),
                result=job.result_json,
                error_code=job.error_code,
                error_message=job.error_message,
                started_at=job.started_at,
                completed_at=job.completed_at,
            ),
            parsed_artifact=cls._to_artifact(artifact) if artifact is not None else None,
        )

    @staticmethod
    def _to_artifact(model: ParsedArtifactModel) -> ParsedArtifact:
        return ParsedArtifact.model_validate(
            {
                "parsed_artifact_id": model.parsed_artifact_id,
                "project_id": model.project_id,
                "source_asset_id": model.source_asset_id,
                "collection_job_id": model.collection_job_id,
                "parser_id": model.parser_id,
                "parser_version": model.parser_version,
                "source_content_hash": model.source_content_hash,
                "fragment_count": model.fragment_count,
                "created_at": model.created_at,
            }
        )

    @staticmethod
    def _to_fragment(model: SourceFragmentModel) -> SourceFragment:
        return SourceFragment.model_validate(
            {
                "source_fragment_id": model.source_fragment_id,
                "parsed_artifact_id": model.parsed_artifact_id,
                "project_id": model.project_id,
                "source_asset_id": model.source_asset_id,
                "ordinal": model.ordinal,
                "locator": model.locator_json,
                "original_excerpt": model.original_excerpt,
                "excerpt_hash": model.excerpt_hash,
                "verification_status": model.verification_status,
                "created_at": model.created_at,
            }
        )
