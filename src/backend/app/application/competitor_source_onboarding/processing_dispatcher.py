"""接入事务提交后，调度已存在的资料处理链路。"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.events import ProjectEventBroker
from app.application.source_requirements import SourceRequirementService
from app.application.source_routing import SourceRoutingService
from app.application.sources import SourceProcessingService
from app.core.errors import AppError
from app.infrastructure.database.models import ProjectEventModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.source_processing import CollectionJobStatus
from app.schemas.source_routing import SourceRoutingAnalyze

SourceProcessingServiceFactory = Callable[[AsyncSession], SourceProcessingService]


class CompetitorSourceProcessingDispatcher:
    """在接入提交后逐项解析来源，并发布可审计的批次结果。"""

    def __init__(
        self,
        database: Database,
        processing_service_factory: SourceProcessingServiceFactory,
        source_routing_service: SourceRoutingService,
        source_requirement_service: SourceRequirementService,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.processing_service_factory = processing_service_factory
        self.source_routing_service = source_routing_service
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
        routing_analyzed_count = 0
        work_count = 0

        for source_asset_id in unique_asset_ids:
            async with self.database.session() as session:
                service = self.processing_service_factory(session)
                try:
                    current = await service.get_status(project_id, source_asset_id)
                    result = current
                    if current.job.status is CollectionJobStatus.QUEUED:
                        claimed_count += 1
                        work_count += 1
                        result = await service.process(project_id, source_asset_id)
                    outcome: dict[str, object] = {
                        "source_asset_id": source_asset_id,
                        "collection_job_id": result.job.collection_job_id,
                        "status": result.job.status.value,
                        "error_code": result.job.error_code,
                    }
                except AppError as exc:
                    outcomes.append(
                        {
                            "source_asset_id": source_asset_id,
                            "status": "dispatch_failed",
                            "error_code": exc.code,
                        }
                    )
                    work_count += 1
                    continue
                except Exception:
                    outcomes.append(
                        {
                            "source_asset_id": source_asset_id,
                            "status": "dispatch_failed",
                            "error_code": "SOURCE_PROCESSING_DISPATCH_FAILED",
                        }
                    )
                    work_count += 1
                    continue

            if result.job.status is CollectionJobStatus.SUCCEEDED:
                try:
                    try:
                        routing = await self.source_routing_service.get(
                            project_id, source_asset_id
                        )
                    except AppError as exc:
                        if exc.code != "SOURCE_ROUTING_NOT_FOUND":
                            raise
                        routing = await self.source_routing_service.analyze(
                            project_id,
                            source_asset_id,
                            SourceRoutingAnalyze(use_model=True, force=False),
                        )
                        routing_analyzed_count += 1
                        work_count += 1
                    outcome.update(
                        {
                            "routing_status": routing.status.value,
                            "routing_confirmed_routes": [
                                item.value for item in routing.confirmed_routes
                            ],
                            "routing_error_code": None,
                        }
                    )
                except AppError as exc:
                    outcome.update(
                        {
                            "routing_status": "failed",
                            "routing_confirmed_routes": [],
                            "routing_error_code": exc.code,
                        }
                    )
                    work_count += 1
                except Exception:
                    outcome.update(
                        {
                            "routing_status": "failed",
                            "routing_confirmed_routes": [],
                            "routing_error_code": "SOURCE_ROUTING_DISPATCH_FAILED",
                        }
                    )
                    work_count += 1
            outcomes.append(outcome)

        # 重复接入若没有待处理资料或缺失路由，不制造重复完成事件。
        if work_count == 0:
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
        routing_confirmed_count = sum(
            item.get("routing_status") == "confirmed" for item in outcomes
        )
        routing_needs_review_count = sum(
            item.get("routing_status") == "needs_review" for item in outcomes
        )
        routing_failed_count = sum(
            item.get("routing_status") == "failed" for item in outcomes
        )
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
                        "routing_analyzed_count": routing_analyzed_count,
                        "routing_confirmed_count": routing_confirmed_count,
                        "routing_needs_review_count": routing_needs_review_count,
                        "routing_failed_count": routing_failed_count,
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
