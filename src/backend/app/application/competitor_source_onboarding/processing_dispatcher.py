"""接入事务提交后，调度已存在的资料处理链路。"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.events import ProjectEventBroker
from app.application.source_requirements import SourceRequirementService
from app.application.sources import SourceProcessingService
from app.core.errors import AppError
from app.infrastructure.database.models import ProjectEventModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.source_processing import CollectionJobStatus

SourceProcessingServiceFactory = Callable[[AsyncSession], SourceProcessingService]


class CompetitorSourceProcessingDispatcher:
    """在接入提交后逐项解析来源，并发布可审计的批次结果。"""

    def __init__(
        self,
        database: Database,
        processing_service_factory: SourceProcessingServiceFactory,
        source_requirement_service: SourceRequirementService,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.processing_service_factory = processing_service_factory
        self.source_requirement_service = source_requirement_service
        self.event_broker = event_broker
        self.trace_id = trace_id

    async def dispatch(
        self,
        project_id: str,
        onboarding_id: str,
        source_asset_ids: Sequence[str],
    ) -> None:
        unique_asset_ids = tuple(dict.fromkeys(source_asset_ids))
        outcomes: list[dict[str, object]] = []
        claimed_count = 0

        for source_asset_id in unique_asset_ids:
            async with self.database.session() as session:
                service = self.processing_service_factory(session)
                try:
                    current = await service.get_status(project_id, source_asset_id)
                    if current.job.status is not CollectionJobStatus.QUEUED:
                        continue
                    claimed_count += 1
                    result = await service.process(project_id, source_asset_id)
                    outcomes.append(
                        {
                            "source_asset_id": source_asset_id,
                            "collection_job_id": result.job.collection_job_id,
                            "status": result.job.status.value,
                            "error_code": result.job.error_code,
                        }
                    )
                except AppError as exc:
                    outcomes.append(
                        {
                            "source_asset_id": source_asset_id,
                            "status": "dispatch_failed",
                            "error_code": exc.code,
                        }
                    )
                except Exception:
                    outcomes.append(
                        {
                            "source_asset_id": source_asset_id,
                            "status": "dispatch_failed",
                            "error_code": "SOURCE_PROCESSING_DISPATCH_FAILED",
                        }
                    )

        # 重复接入若没有可领取任务，不制造重复的完成事件。
        if claimed_count == 0:
            return

        assessment_error: str | None = None
        assessment_status: str | None = None
        assessment_input_hash: str | None = None
        missing_required_count: int | None = None
        try:
            assessment = await self.source_requirement_service.get(project_id)
            assessment_status = assessment.status.value
            assessment_input_hash = assessment.input_hash
            missing_required_count = assessment.missing_required_count
        except AppError as exc:
            assessment_error = exc.code
        except Exception:
            assessment_error = "SOURCE_REQUIREMENT_REEVALUATION_FAILED"

        completed_count = sum(item["status"] == "succeeded" for item in outcomes)
        blocked_count = sum(item["status"] == "blocked" for item in outcomes)
        failed_count = len(outcomes) - completed_count - blocked_count
        now = datetime.now(UTC)
        async with self.database.session() as session:
            repository = ProjectRepository(session)
            await repository.add_event(
                ProjectEventModel(
                    event_id=f"evt_{uuid4().hex[:16]}",
                    project_id=project_id,
                    sequence_number=0,
                    event_type="competitor_source_processing_completed",
                    data_json={
                        "onboarding_id": onboarding_id,
                        "requested_source_count": len(unique_asset_ids),
                        "claimed_queued_count": claimed_count,
                        "succeeded_count": completed_count,
                        "blocked_count": blocked_count,
                        "failed_count": failed_count,
                        "outcomes": outcomes,
                        "source_requirements_status": assessment_status,
                        "source_requirements_input_hash": assessment_input_hash,
                        "missing_required_count": missing_required_count,
                        "source_requirements_error": assessment_error,
                    },
                    trace_id=self.trace_id,
                    created_at=now,
                )
            )
            try:
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise
        await self.event_broker.notify(project_id)
