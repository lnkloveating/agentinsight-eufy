import asyncio

from fastapi.testclient import TestClient

from app.application.events import EventService
from app.infrastructure.database import Database

from .test_project_lifecycle import project_payload


def test_event_history_and_last_event_cursor(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json=project_payload()).json()
    project_id = project["project_id"]
    database: Database = client.app.state.database
    broker = client.app.state.event_broker
    settings = client.app.state.settings
    service = EventService(database, broker, settings.sse_heartbeat_seconds)

    async def read_events() -> None:
        stream = service.stream(project_id, after_sequence=0)
        first_event = await anext(stream)
        assert first_event is not None
        assert first_event.event_type == "project_created"
        assert first_event.sequence_number == 1
        await stream.aclose()

        cursor = await service.resolve_after_sequence(project_id, first_event.event_id)
        assert cursor == 1

    asyncio.run(read_events())


def test_invalid_last_event_id_returns_conflict(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json=project_payload()).json()
    response = client.get(
        f"/api/v1/projects/{project['project_id']}/events",
        headers={"Last-Event-ID": "evt_missing"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LAST_EVENT_NOT_FOUND"
