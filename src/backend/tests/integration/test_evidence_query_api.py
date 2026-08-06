import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.infrastructure.database.models import (
    ClaimEvidenceLinkModel,
    ClaimModel,
    EvidenceModel,
)


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


def _evidence(evidence_id: str, project_id: str, status: str, source_type: str) -> EvidenceModel:
    now = datetime.now(UTC)
    return EvidenceModel(
        evidence_id=evidence_id,
        project_id=project_id,
        source_url=f"https://example.com/{evidence_id}",
        normalized_source_url=f"https://example.com/{evidence_id}",
        source_domain="example.com",
        source_type=source_type,
        title=evidence_id,
        original_excerpt=f"Excerpt for {evidence_id}",
        claim_type="fact",
        collected_at=now,
        status=status,
        content_hash=evidence_id.removeprefix("ev_").ljust(64, "0"),
        confidence=0.9,
        authority_score=0.9,
        recency_score=0.9,
        diversity_score=0.9,
    )


def test_evidence_and_claim_query_endpoints_use_persisted_records(client: TestClient) -> None:
    project_id = client.post("/api/v1/projects", json=_project_payload()).json()["project_id"]

    async def seed_records() -> None:
        async with client.app.state.database.session() as session:
            session.add_all(
                [
                    _evidence("ev_official", project_id, "verified", "official"),
                    _evidence("ev_mock", project_id, "mock", "community"),
                    ClaimModel(
                        claim_id="claim_package",
                        project_id=project_id,
                        statement="包裹事件需要结合上下文判断风险。",
                        claim_type="fact",
                        scope_json={"scenario": "package"},
                        status="supported",
                    ),
                    ClaimEvidenceLinkModel(
                        link_id="link_package",
                        project_id=project_id,
                        claim_id="claim_package",
                        evidence_id="ev_official",
                        relation_type="supports",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed_records())

    evidence_response = client.get(
        f"/api/v1/projects/{project_id}/evidence",
        params={"status": "verified", "source_type": "official"},
    )
    assert evidence_response.status_code == 200
    evidence_page = evidence_response.json()
    assert evidence_page["total"] == 1
    assert [item["evidence_id"] for item in evidence_page["items"]] == ["ev_official"]
    assert evidence_page["items"][0]["original_excerpt"] == "Excerpt for ev_official"

    claims_response = client.get(f"/api/v1/projects/{project_id}/claims")
    assert claims_response.status_code == 200
    assert claims_response.json() == [
        {
            "claim_id": "claim_package",
            "statement": "包裹事件需要结合上下文判断风险。",
            "claim_type": "fact",
            "evidence_ids": ["ev_official"],
            "contradicting_evidence_ids": [],
            "scope": {"scenario": "package"},
            "status": "supported",
        }
    ]


def test_evidence_query_rejects_unknown_project(client: TestClient) -> None:
    response = client.get("/api/v1/projects/proj_missing/evidence")

    assert response.status_code == 404
    assert response.json()["code"] == "PROJECT_NOT_FOUND"


def test_evidence_query_cursor_does_not_repeat_records(client: TestClient) -> None:
    project_id = client.post("/api/v1/projects", json=_project_payload()).json()["project_id"]

    async def seed_page() -> None:
        async with client.app.state.database.session() as session:
            session.add_all(
                [
                    _evidence(f"ev_{index:03d}", project_id, "verified", "official")
                    for index in range(51)
                ]
            )
            await session.commit()

    asyncio.run(seed_page())

    first = client.get(f"/api/v1/projects/{project_id}/evidence").json()
    second = client.get(
        f"/api/v1/projects/{project_id}/evidence",
        params={"cursor": first["next_cursor"]},
    ).json()

    assert first["total"] == 51
    assert len(first["items"]) == 50
    assert first["next_cursor"] is not None
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    assert second["items"][0]["evidence_id"] not in {
        item["evidence_id"] for item in first["items"]
    }
