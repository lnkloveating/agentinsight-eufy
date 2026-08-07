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
from app.schemas.source import SourceAssetKind, SourceAssetStatus
from app.schemas.source_processing import (
    CollectionJobStatus,
    ParsedArtifact,
    SourceFragment,
    SourceFragmentPage,
    SourceFragmentVerificationStatus,
    SourceProcessingJob,
    SourceProcessingStatus,
)
from app.sources.parsers import SourceParserError, SourceParserRegistry


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
        try:
            if asset.kind == SourceAssetKind.LINK:
                raise SourceParserError(
                    "SOURCE_CONNECTOR_NOT_CONFIGURED",
                    "Registered links require an explicit web connector before processing.",
                    blocked=True,
                )
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
            workspace = materialized.workspace
            if materialized.content_hash != asset.content_hash:
                raise SourceParserError(
                    "SOURCE_CONTENT_HASH_MISMATCH",
                    "The stored source no longer matches its registered content hash.",
                )
            parser = self.parsers.get(asset.media_type)
            parsed = parser.parse(materialized.source_path)
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
            # This is a second read of the isolated source snapshot. No LLM output can
            # satisfy this check without matching the original bytes or extracted page.
            parser.verify(materialized.source_path, parsed.fragments)

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
                    verification_status=SourceFragmentVerificationStatus.VERIFIED,
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
                "verification": "deterministic",
            }
            job.completed_at = completed_at
            job.updated_at = completed_at
            await self._add_event(
                asset, job, "source_processing_succeeded", completed_at
            )
            await self.repository.commit()
            await self.event_broker.notify(project_id)
            return self._to_status(asset, job, artifact)
        except SourceParserError as exc:
            await self.repository.rollback()
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

    async def _finish_error(
        self,
        asset: SourceAssetModel,
        job: CollectionJobModel,
        *,
        code: str,
        message: str,
        blocked: bool,
    ) -> SourceProcessingStatus:
        now = datetime.now(UTC)
        job.status = (
            CollectionJobStatus.BLOCKED if blocked else CollectionJobStatus.FAILED
        )
        job.result_json = {
            "source_asset_id": asset.source_asset_id,
            "progress": 100,
            "coverage_gap": True,
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
