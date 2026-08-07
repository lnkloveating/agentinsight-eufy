"""外部采集任务状态和失败审计用例。"""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import CollectionJobModel, ProjectEventModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import (
    CollectionJob,
    CollectionJobCreate,
    CollectionJobFailure,
)
from app.schemas.source_processing import CollectionJobStatus


class CollectionJobService:
    def __init__(
        self,
        repository: EvidenceRepository,
        project_repository: ProjectRepository,
        trace_id: str,
        event_broker: ProjectEventBroker,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.trace_id = trace_id
        self.event_broker = event_broker

    async def create(self, project_id: str, payload: CollectionJobCreate) -> CollectionJob:
        if not await self.repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )
        now = datetime.now(UTC)
        model = CollectionJobModel(
            collection_job_id=f"collect_{uuid4().hex[:16]}",
            project_id=project_id,
            task_id=payload.task_id,
            source_url=str(payload.source_url) if payload.source_url is not None else None,
            source_type=payload.source_type,
            status=CollectionJobStatus.QUEUED,
            attempt_count=0,
            result_json={},
            created_at=now,
            updated_at=now,
        )
        try:
            await self.repository.add_collection_job(model)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return self._to_collection_job(model)

    async def record_failure(
        self, collection_job_id: str, payload: CollectionJobFailure
    ) -> CollectionJob:
        model = await self.repository.get_collection_job(collection_job_id)
        if model is None:
            raise AppError(
                code="COLLECTION_JOB_NOT_FOUND",
                message="采集任务不存在。",
                status_code=404,
                details={"collection_job_id": collection_job_id},
            )
        now = datetime.now(UTC)
        model.status = CollectionJobStatus.FAILED
        model.attempt_count = payload.attempt_count
        model.error_code = payload.error_code
        model.error_message = payload.error_message
        model.result_json = payload.result
        model.completed_at = now
        model.updated_at = now
        event = ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=model.project_id,
            sequence_number=0,
            event_type="evidence_collection_failed",
            data_json={
                "collection_job_id": model.collection_job_id,
                "task_id": model.task_id,
                "source_url": model.source_url,
                "source_type": model.source_type,
                "attempt_count": model.attempt_count,
                "error_code": model.error_code,
                "error_message": model.error_message,
                "coverage_gap": True,
            },
            trace_id=self.trace_id,
            created_at=now,
        )
        try:
            await self.project_repository.add_event(event)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(model.project_id)
        return self._to_collection_job(model)

    @staticmethod
    def _to_collection_job(model: CollectionJobModel) -> CollectionJob:
        return CollectionJob.model_validate(
            {
                "collection_job_id": model.collection_job_id,
                "project_id": model.project_id,
                "task_id": model.task_id,
                "source_url": model.source_url,
                "source_type": model.source_type,
                "status": model.status,
                "attempt_count": model.attempt_count,
                "result": model.result_json,
                "error_code": model.error_code,
                "error_message": model.error_message,
                "started_at": model.started_at,
                "completed_at": model.completed_at,
            }
        )
