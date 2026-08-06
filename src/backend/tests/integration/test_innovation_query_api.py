import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.infrastructure.database.models import InnovationModel


def _project_payload() -> dict[str, object]:
    return {
        "brief": {
            "question": "智能门铃是否应该理解包裹风险？",
            "category": "家庭安防",
            "target_user": "智能门铃用户",
            "region": "北美",
            "scenarios": ["包裹送达"],
            "constraints": ["隐私优先"],
            "focus_dimensions": ["证据", "技术"],
        }
    }


def test_innovation_query_is_empty_without_agent_output(client: TestClient) -> None:
    project_id = client.post("/api/v1/projects", json=_project_payload()).json()["project_id"]

    response = client.get(f"/api/v1/projects/{project_id}/innovations")

    assert response.status_code == 200
    assert response.json() == []


def test_innovation_query_returns_only_persisted_candidate(client: TestClient) -> None:
    project_id = client.post("/api/v1/projects", json=_project_payload()).json()["project_id"]

    async def seed_candidate() -> None:
        now = datetime.now(UTC)
        async with client.app.state.database.session() as session:
            session.add(
                InnovationModel(
                    innovation_id="inv_persisted",
                    project_id=project_id,
                    name="Persisted candidate",
                    status="tech_review",
                    target_user_json={"persona_ids": [], "description": "Doorbell owner"},
                    problem_json={"pain_ids": [], "description": "Notifications lack context"},
                    event_understanding_json={
                        "base_event": {"type": "package_delivered", "source": "doorbell"},
                        "event_state": {
                            "type": "package_still_present",
                            "source": "doorbell",
                        },
                        "context_signals": [
                            {
                                "type": signal_type,
                                "source": f"source:{signal_type}",
                                "availability": "available",
                                "authorization": "authorized",
                                "freshness": "five minutes",
                                "latency_ms": 100,
                                "confidence": 0.9,
                                "fallback": "inconclusive",
                            }
                            for signal_type in ["weather", "package_presence"]
                        ],
                        "inference": "Possible exposure",
                        "risk_or_value": "Weather damage",
                        "recommended_action": "Review the event",
                    },
                    competitor_gap_ids_json=[],
                    technical_assessment_json={},
                    business_assessment_json={},
                    red_team_review_json=None,
                    evidence_ids_json=["ev_real"],
                    score_breakdown_json={},
                    base_score=0,
                    final_score=0,
                    gate_issues_json=[],
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

    asyncio.run(seed_candidate())
    response = client.get(f"/api/v1/projects/{project_id}/innovations")

    assert response.status_code == 200
    assert [item["innovation_id"] for item in response.json()] == ["inv_persisted"]
