"""用户授权原始资料的登记、去重、隔离存储与删除用例。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.models import (
    CollectionJobModel,
    ProjectEventModel,
    SourceAssetModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.infrastructure.source_storage import AsyncUploadStream, LocalSourceStorage, StoredSource
from app.schemas.source import (
    SourceAsset,
    SourceAssetIngestResult,
    SourceAssetKind,
    SourceAssetPage,
    SourceAssetStatus,
    SourceFileMetadata,
    SourceLinkCreate,
    SourceMediaCategory,
)
from app.schemas.source_processing import CollectionJobStatus
from app.sources.validation import (
    SourceFileProfile,
    classify_source_file,
    normalize_public_url,
    source_url_hash,
)


class SourceAssetService:
    def __init__(
        self,
        repository: SourceAssetRepository,
        project_repository: ProjectRepository,
        storage: LocalSourceStorage,
        trace_id: str,
        event_broker: ProjectEventBroker,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.storage = storage
        self.trace_id = trace_id
        self.event_broker = event_broker

    async def upload_file(
        self,
        project_id: str,
        *,
        filename: str | None,
        declared_media_type: str | None,
        metadata: SourceFileMetadata,
        stream: AsyncUploadStream,
    ) -> SourceAssetIngestResult:
        await self._require_project(project_id)
        self._require_authorization(metadata.authorization_confirmed)
        profile = classify_source_file(filename, declared_media_type)
        source_asset_id = f"source_{uuid4().hex[:16]}"
        stored = await self.storage.save(
            project_id=project_id,
            source_asset_id=source_asset_id,
            suffix=profile.suffix,
            stream=stream,
        )
        existing = await self.repository.get_by_hash(
            project_id, SourceAssetKind.FILE, stored.content_hash
        )
        if existing is not None and existing.status == SourceAssetStatus.READY:
            self.storage.delete(stored.storage_key)
            return SourceAssetIngestResult(
                source_asset=self._to_source_asset(existing), created=False
            )
        now = datetime.now(UTC)
        try:
            if existing is not None:
                await self._restore_file(existing, profile, stored, metadata, now)
                asset = existing
                created = False
            else:
                asset = await self._create_asset(
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    kind=SourceAssetKind.FILE,
                    display_name=profile.display_name,
                    original_filename=profile.display_name,
                    source_url=None,
                    normalized_source_url=None,
                    storage_key=stored.storage_key,
                    media_type=profile.media_type,
                    media_category=profile.media_category,
                    content_hash=stored.content_hash,
                    byte_size=stored.byte_size,
                    authorization_basis=metadata.authorization_basis,
                    authorized_by=metadata.authorized_by,
                    purpose=metadata.purpose,
                    now=now,
                )
                created = True
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            self.storage.delete(stored.storage_key)
            duplicate = await self.repository.get_by_hash(
                project_id, SourceAssetKind.FILE, stored.content_hash
            )
            if duplicate is None:
                raise
            return SourceAssetIngestResult(
                source_asset=self._to_source_asset(duplicate), created=False
            )
        except Exception:
            await self.repository.rollback()
            self.storage.delete(stored.storage_key)
            raise
        await self.event_broker.notify(project_id)
        return SourceAssetIngestResult(source_asset=self._to_source_asset(asset), created=created)

    async def create_link(
        self, project_id: str, payload: SourceLinkCreate
    ) -> SourceAssetIngestResult:
        await self._require_project(project_id)
        normalized_url = normalize_public_url(str(payload.source_url))
        content_hash = source_url_hash(normalized_url)
        existing = await self.repository.get_by_hash(
            project_id, SourceAssetKind.LINK, content_hash
        )
        if existing is not None and existing.status == SourceAssetStatus.READY:
            return SourceAssetIngestResult(
                source_asset=self._to_source_asset(existing), created=False
            )
        now = datetime.now(UTC)
        try:
            if existing is not None:
                await self._restore_link(existing, payload, normalized_url, now)
                asset = existing
                created = False
            else:
                asset = await self._create_asset(
                    project_id=project_id,
                    source_asset_id=f"source_{uuid4().hex[:16]}",
                    kind=SourceAssetKind.LINK,
                    display_name=payload.display_name,
                    original_filename=None,
                    source_url=str(payload.source_url),
                    normalized_source_url=normalized_url,
                    storage_key=None,
                    media_type="text/html",
                    media_category=SourceMediaCategory.WEBPAGE,
                    content_hash=content_hash,
                    byte_size=0,
                    authorization_basis=payload.authorization_basis,
                    authorized_by=payload.authorized_by,
                    purpose=payload.purpose,
                    now=now,
                )
                created = True
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            duplicate = await self.repository.get_by_hash(
                project_id, SourceAssetKind.LINK, content_hash
            )
            if duplicate is None:
                raise
            return SourceAssetIngestResult(
                source_asset=self._to_source_asset(duplicate), created=False
            )
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(project_id)
        return SourceAssetIngestResult(source_asset=self._to_source_asset(asset), created=created)

    async def get(self, project_id: str, source_asset_id: str) -> SourceAsset:
        await self._require_project(project_id)
        model = await self.repository.get_by_project(project_id, source_asset_id)
        if model is None:
            raise AppError(
                code="SOURCE_ASSET_NOT_FOUND",
                message="原始资料不存在。",
                status_code=404,
                details={"source_asset_id": source_asset_id},
            )
        return self._to_source_asset(model)

    async def list(
        self,
        project_id: str,
        *,
        cursor: str | None = None,
        kind: SourceAssetKind | None = None,
        status: SourceAssetStatus | None = None,
    ) -> SourceAssetPage:
        await self._require_project(project_id)
        models, next_cursor, total = await self.repository.list_assets(
            project_id,
            cursor=cursor,
            kind=kind,
            status=status,
        )
        return SourceAssetPage(
            items=[self._to_source_asset(model) for model in models],
            next_cursor=next_cursor,
            total=total,
        )

    async def delete(self, project_id: str, source_asset_id: str) -> SourceAsset:
        await self._require_project(project_id)
        model = await self.repository.get_by_project(project_id, source_asset_id)
        if model is None:
            raise AppError(
                code="SOURCE_ASSET_NOT_FOUND",
                message="原始资料不存在。",
                status_code=404,
                details={"source_asset_id": source_asset_id},
            )
        if model.status == SourceAssetStatus.DELETED:
            return self._to_source_asset(model)
        now = datetime.now(UTC)
        self.storage.delete(model.storage_key)
        await self.repository.delete_processing_for_source(project_id, source_asset_id)
        model.storage_key = None
        model.status = SourceAssetStatus.DELETED
        model.deleted_at = now
        model.updated_at = now
        collection_job = await self.repository.get_collection_job(model.collection_job_id)
        if collection_job is not None and collection_job.status in {
            CollectionJobStatus.QUEUED,
            CollectionJobStatus.RUNNING,
            CollectionJobStatus.SUCCEEDED,
            CollectionJobStatus.PARTIAL,
        }:
            collection_job.status = CollectionJobStatus.BLOCKED
            collection_job.error_code = "SOURCE_ASSET_DELETED"
            collection_job.error_message = "原始资料已删除，任务不会交给外部 Runtime。"
            collection_job.completed_at = now
            collection_job.updated_at = now
            collection_job.result_json = {
                "source_asset_id": source_asset_id,
                "progress": 100,
                "parsed_content_purged": True,
            }
        await self._add_event(model, "source_asset_deleted", now)
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(project_id)
        return self._to_source_asset(model)

    async def _create_asset(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        kind: SourceAssetKind,
        display_name: str,
        original_filename: str | None,
        source_url: str | None,
        normalized_source_url: str | None,
        storage_key: str | None,
        media_type: str,
        media_category: SourceMediaCategory,
        content_hash: str,
        byte_size: int,
        authorization_basis: str,
        authorized_by: str,
        purpose: str,
        now: datetime,
    ) -> SourceAssetModel:
        collection_job_id = f"collect_{uuid4().hex[:16]}"
        await self.repository.add_collection_job(
            self._collection_job(
                collection_job_id=collection_job_id,
                project_id=project_id,
                source_asset_id=source_asset_id,
                source_url=normalized_source_url,
                source_type=media_category,
                now=now,
            )
        )
        model = SourceAssetModel(
            source_asset_id=source_asset_id,
            project_id=project_id,
            collection_job_id=collection_job_id,
            kind=kind,
            status=SourceAssetStatus.READY,
            display_name=display_name,
            original_filename=original_filename,
            source_url=source_url,
            normalized_source_url=normalized_source_url,
            storage_key=storage_key,
            media_type=media_type,
            media_category=media_category,
            content_hash=content_hash,
            byte_size=byte_size,
            authorization_basis=authorization_basis,
            authorization_confirmed_at=now,
            authorized_by=authorized_by,
            purpose=purpose,
            created_at=now,
            updated_at=now,
        )
        await self.repository.add_source_asset(model)
        await self._add_event(model, "source_asset_created", now)
        return model

    async def _restore_file(
        self,
        model: SourceAssetModel,
        profile: SourceFileProfile,
        stored: StoredSource,
        metadata: SourceFileMetadata,
        now: datetime,
    ) -> None:
        await self._replace_collection_job(model, profile.media_category, None, now)
        model.status = SourceAssetStatus.READY
        model.display_name = profile.display_name
        model.original_filename = profile.display_name
        model.storage_key = stored.storage_key
        model.media_type = profile.media_type
        model.media_category = profile.media_category
        model.byte_size = stored.byte_size
        model.authorization_basis = metadata.authorization_basis
        model.authorization_confirmed_at = now
        model.authorized_by = metadata.authorized_by
        model.purpose = metadata.purpose
        model.updated_at = now
        model.deleted_at = None
        await self._add_event(model, "source_asset_restored", now)

    async def _restore_link(
        self,
        model: SourceAssetModel,
        payload: SourceLinkCreate,
        normalized_url: str,
        now: datetime,
    ) -> None:
        await self._replace_collection_job(
            model, SourceMediaCategory.WEBPAGE, normalized_url, now
        )
        model.status = SourceAssetStatus.READY
        model.display_name = payload.display_name
        model.source_url = str(payload.source_url)
        model.normalized_source_url = normalized_url
        model.authorization_basis = payload.authorization_basis
        model.authorization_confirmed_at = now
        model.authorized_by = payload.authorized_by
        model.purpose = payload.purpose
        model.updated_at = now
        model.deleted_at = None
        await self._add_event(model, "source_asset_restored", now)

    async def _replace_collection_job(
        self,
        model: SourceAssetModel,
        source_type: SourceMediaCategory,
        source_url: str | None,
        now: datetime,
    ) -> None:
        collection_job_id = f"collect_{uuid4().hex[:16]}"
        await self.repository.add_collection_job(
            self._collection_job(
                collection_job_id=collection_job_id,
                project_id=model.project_id,
                source_asset_id=model.source_asset_id,
                source_url=source_url,
                source_type=source_type,
                now=now,
            )
        )
        model.collection_job_id = collection_job_id

    @staticmethod
    def _collection_job(
        *,
        collection_job_id: str,
        project_id: str,
        source_asset_id: str,
        source_url: str | None,
        source_type: SourceMediaCategory,
        now: datetime,
    ) -> CollectionJobModel:
        return CollectionJobModel(
            collection_job_id=collection_job_id,
            project_id=project_id,
            source_url=source_url,
            source_type=source_type,
            status=CollectionJobStatus.QUEUED,
            attempt_count=0,
            result_json={"source_asset_id": source_asset_id},
            created_at=now,
            updated_at=now,
        )

    async def _add_event(
        self, model: SourceAssetModel, event_type: str, now: datetime
    ) -> None:
        await self.project_repository.add_event(
            ProjectEventModel(
                event_id=f"evt_{uuid4().hex[:16]}",
                project_id=model.project_id,
                sequence_number=0,
                event_type=event_type,
                data_json={
                    "source_asset_id": model.source_asset_id,
                    "collection_job_id": model.collection_job_id,
                    "kind": model.kind,
                    "media_category": model.media_category,
                    "status": model.status,
                },
                trace_id=self.trace_id,
                created_at=now,
            )
        )

    async def _require_project(self, project_id: str) -> None:
        if not await self.repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )

    @staticmethod
    def _require_authorization(confirmed: bool) -> None:
        if not confirmed:
            raise AppError(
                code="SOURCE_AUTHORIZATION_REQUIRED",
                message="必须确认拥有资料或已获得研究使用授权。",
                status_code=422,
            )

    @staticmethod
    def _to_source_asset(model: SourceAssetModel) -> SourceAsset:
        return SourceAsset.model_validate(
            {
                "source_asset_id": model.source_asset_id,
                "project_id": model.project_id,
                "kind": model.kind,
                "status": model.status,
                "display_name": model.display_name,
                "original_filename": model.original_filename,
                "source_url": model.source_url,
                "media_type": model.media_type,
                "media_category": model.media_category,
                "content_hash": model.content_hash,
                "byte_size": model.byte_size,
                "authorization_basis": model.authorization_basis,
                "authorization_confirmed_at": model.authorization_confirmed_at,
                "authorized_by": model.authorized_by,
                "purpose": model.purpose,
                "collection_job_id": model.collection_job_id,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
                "deleted_at": model.deleted_at,
            }
        )
