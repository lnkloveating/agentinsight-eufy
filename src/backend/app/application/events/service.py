"""持久化项目事件的回放与实时订阅。"""

from collections.abc import AsyncIterator

from app.application.events.broker import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.project import ProjectEvent


class EventService:
    """从数据库顺序读取事件，并通过 Broker 等待新事件。"""

    def __init__(
        self,
        database: Database,
        broker: ProjectEventBroker,
        heartbeat_seconds: float,
    ) -> None:
        self.database = database
        self.broker = broker
        self.heartbeat_seconds = heartbeat_seconds

    async def ensure_project_exists(self, project_id: str) -> None:
        async with self.database.session() as session:
            repository = ProjectRepository(session)
            if await repository.get_project(project_id) is None:
                raise AppError(
                    code="PROJECT_NOT_FOUND",
                    message="没有找到指定的研究项目。",
                    status_code=404,
                    details={"project_id": project_id},
                )

    async def stream(
        self,
        project_id: str,
        after_sequence: int,
    ) -> AsyncIterator[ProjectEvent | None]:
        """按顺序产生事件；None 表示应发送一条 SSE 心跳。"""
        known_version = self.broker.current_version(project_id)

        while True:
            events = await self._read_events(project_id, after_sequence)
            if events:
                for event in events:
                    after_sequence = event.sequence_number
                    yield event
                continue

            known_version, timed_out = await self.broker.wait_for_change(
                project_id,
                known_version,
                self.heartbeat_seconds,
            )
            if timed_out:
                yield None

    async def resolve_after_sequence(
        self,
        project_id: str,
        last_event_id: str | None,
    ) -> int:
        if last_event_id is None:
            return 0
        async with self.database.session() as session:
            repository = ProjectRepository(session)
            sequence = await repository.get_event_sequence(project_id, last_event_id)
        if sequence is None:
            raise AppError(
                code="LAST_EVENT_NOT_FOUND",
                message="无法识别 Last-Event-ID，请重新建立完整事件订阅。",
                status_code=409,
                details={"project_id": project_id, "last_event_id": last_event_id},
            )
        return sequence

    async def _read_events(self, project_id: str, after_sequence: int) -> list[ProjectEvent]:
        async with self.database.session() as session:
            repository = ProjectRepository(session)
            models = await repository.list_events(project_id, after_sequence=after_sequence)
        return [
            ProjectEvent(
                event_id=model.event_id,
                event_type=model.event_type,
                project_id=model.project_id,
                sequence_number=model.sequence_number,
                timestamp=model.created_at,
                data=model.data_json,
                trace_id=model.trace_id,
            )
            for model in models
        ]
