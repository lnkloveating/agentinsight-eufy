import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.infrastructure.database.models import EvidenceModel, HouseholdSnapshotModel
from app.main import create_app
from tests.research_brief import home_safety_brief_payload


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auto_create_schema=True,
        model_credentials_env_file=None,
    )


def _project(client: TestClient, question: str) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "brief": home_safety_brief_payload(question)
        },
    )
    assert response.status_code == 201
    return str(response.json()["project_id"])


async def _seed_evidence(
    application: object,
    project_id: str,
    statuses: dict[str, str],
) -> None:
    now = datetime.now(UTC)
    async with application.state.database.session() as session:
        for index, (evidence_id, status) in enumerate(statuses.items()):
            session.add(
                EvidenceModel(
                    evidence_id=evidence_id,
                    project_id=project_id,
                    collection_job_id=None,
                    source_url=f"https://example.com/device/{index}",
                    normalized_source_url=f"https://example.com/device/{index}",
                    source_domain="example.com",
                    source_asset_id=None,
                    source_fragment_id=None,
                    source_locator_json=None,
                    source_type="official_product",
                    title=f"Official device evidence {index}",
                    original_excerpt=f"Evidence statement {index}",
                    claim_type="capability",
                    product="eufy E340",
                    region="US",
                    user_segment=None,
                    published_at=None,
                    collected_at=now,
                    status=status,
                    content_hash=f"{project_id}-{index}".ljust(64, "0")[:64],
                    confidence=0.9,
                    authority_score=0.9,
                    recency_score=0.8,
                    diversity_score=0.7,
                )
            )
        await session.commit()


def _capability(
    key: str,
    evidence_id: str,
    *,
    assertion: str = "supported",
    availability: str = "available",
    offline_support: str = "none",
) -> dict[str, object]:
    return {
        "capability_key": key,
        "capability_name": key.replace(".", " "),
        "kind": "sensor",
        "assertion": assertion,
        "availability": availability,
        "confidence": 0.9,
        "evidence_ids": [evidence_id],
        "latency_ms_max": 2500,
        "data_scope": "device_local",
        "authorization_required": True,
        "offline_support": offline_support,
        "fallback": None,
    }


def _catalog_payload() -> dict[str, object]:
    return {
        "manufacturer": "eufy",
        "product_name": "Video Doorbell E340",
        "model": "E340",
        "category": "doorbell",
        "lifecycle_status": "active",
        "identity_evidence_ids": ["evidence_identity"],
        "capabilities": [
            _capability("vision.package_presence", "evidence_supported"),
            _capability("weather.risk", "evidence_supported"),
            _capability(
                "weather.risk",
                "evidence_limitation",
                assertion="unsupported",
                availability="unavailable",
            ),
        ],
    }


def _snapshot_payload(
    catalog_device_id: str, *, runtime_status: str = "online"
) -> dict[str, object]:
    return {
        "authorization_confirmed": True,
        "authorized_by": "research-lead",
        "purpose": "Check capability coverage without retaining household media.",
        "locations": [
            {"location_id": "front_door", "label": "Front door", "location_type": "entrance"}
        ],
        "devices": [
            {
                "household_device_id": "home_device_doorbell",
                "catalog_device_id": catalog_device_id,
                "display_name": "Front doorbell",
                "category": "doorbell",
                "model": "E340",
                "location_id": "front_door",
                "runtime_status": runtime_status,
                "authorization_status": "authorized",
            }
        ],
        "relations": [],
    }


def test_device_catalog_snapshot_and_query_are_evidence_bounded() -> None:
    application = create_app(_settings())
    with TestClient(application) as client:
        project_id = _project(client, "Can eufy support an AI-native package protection ecosystem?")
        other_project_id = _project(client, "Other isolated research")
        asyncio.run(
            _seed_evidence(
                application,
                project_id,
                {
                    "evidence_identity": "verified",
                    "evidence_supported": "verified",
                    "evidence_limitation": "partially_verified",
                    "evidence_unreviewed": "unverified",
                },
            )
        )
        asyncio.run(
            _seed_evidence(
                application,
                other_project_id,
                {"evidence_other_project": "verified"},
            )
        )

        unreviewed_payload = _catalog_payload()
        unreviewed_payload["identity_evidence_ids"] = ["evidence_unreviewed"]
        unreviewed = client.post(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog",
            json=unreviewed_payload,
        )
        cross_project_payload = _catalog_payload()
        cross_project_payload["identity_evidence_ids"] = ["evidence_other_project"]
        cross_project = client.post(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog",
            json=cross_project_payload,
        )
        created = client.post(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog",
            json=_catalog_payload(),
        )
        assert created.status_code == 201
        device = created.json()
        catalog_device_id = device["catalog_device_id"]

        listed = client.get(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog"
        )
        fetched = client.get(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog/{catalog_device_id}"
        )
        replacement_payload = _catalog_payload()
        replacement_payload["product_name"] = "Video Doorbell E340 (verified record)"
        replaced = client.put(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog/{catalog_device_id}",
            json=replacement_payload,
        )
        isolated = client.get(
            f"/api/v1/projects/{other_project_id}/device-capabilities/catalog/{catalog_device_id}"
        )
        snapshot = client.put(
            f"/api/v1/projects/{project_id}/device-capabilities/household-snapshot",
            json=_snapshot_payload(catalog_device_id),
        )
        query = client.post(
            f"/api/v1/projects/{project_id}/device-capabilities/queries",
            json={
                "requirements": [
                    {
                        "capability_key": "vision.package_presence",
                        "location_id": "front_door",
                        "kind": "sensor",
                    },
                    {
                        "capability_key": "weather.risk",
                        "location_id": "front_door",
                        "kind": "sensor",
                    },
                    {
                        "capability_key": "presence.household",
                        "location_id": "front_door",
                        "kind": "context",
                    },
                ]
            },
        )

        async def expire_capability_evidence() -> None:
            async with application.state.database.session() as session:
                evidence = await session.get(EvidenceModel, "evidence_supported")
                assert evidence is not None
                evidence.status = "outdated"
                await session.commit()

        asyncio.run(expire_capability_evidence())
        stale_query = client.post(
            f"/api/v1/projects/{project_id}/device-capabilities/queries",
            json={
                "requirements": [
                    {
                        "capability_key": "vision.package_presence",
                        "location_id": "front_door",
                        "kind": "sensor",
                    }
                ]
            },
        )
        delete_in_use = client.delete(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog/{catalog_device_id}"
        )

    assert unreviewed.status_code == 422
    assert unreviewed.json()["code"] == "DEVICE_CAPABILITY_EVIDENCE_INVALID"
    assert unreviewed.json()["details"]["ineligible_evidence_statuses"] == {
        "evidence_unreviewed": "unverified"
    }
    assert cross_project.status_code == 422
    assert cross_project.json()["details"]["missing_or_cross_project_evidence_ids"] == [
        "evidence_other_project"
    ]
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert fetched.status_code == 200
    assert fetched.json()["catalog_device_id"] == catalog_device_id
    assert replaced.status_code == 200
    assert replaced.json()["product_name"] == "Video Doorbell E340 (verified record)"
    assert isolated.status_code == 404
    assert snapshot.status_code == 200
    assert snapshot.json()["version"] == 1
    assert query.status_code == 200
    result = query.json()
    statuses = {
        item["requirement"]["capability_key"]: item["status"]
        for item in result["requirements"]
    }
    assert statuses == {
        "vision.package_presence": "available",
        "weather.risk": "conflict",
        "presence.household": "unknown",
    }
    assert result["overall_status"] == "conflict"
    assert result["cited_evidence_ids"] == [
        "evidence_limitation",
        "evidence_supported",
    ]
    assert stale_query.status_code == 200
    assert stale_query.json()["overall_status"] == "unknown"
    assert stale_query.json()["requirements"][0]["issues"] == [
        "CAPABILITY_EVIDENCE_STALE",
        "CAPABILITY_HAS_NO_CURRENT_EVIDENCE",
    ]
    assert stale_query.json()["cited_evidence_ids"] == []
    assert delete_in_use.status_code == 409
    assert delete_in_use.json()["code"] == "DEVICE_CATALOG_IN_USE"


def test_snapshot_updates_are_versioned_and_unreferenced_catalog_can_be_deleted() -> None:
    application = create_app(_settings())
    with TestClient(application) as client:
        project_id = _project(client, "Version household capability coverage")
        asyncio.run(
            _seed_evidence(
                application,
                project_id,
                {
                    "evidence_identity": "verified",
                    "evidence_supported": "verified",
                    "evidence_limitation": "partially_verified",
                },
            )
        )
        created = client.post(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog",
            json=_catalog_payload(),
        )
        assert created.status_code == 201
        catalog_device_id = created.json()["catalog_device_id"]
        first = client.put(
            f"/api/v1/projects/{project_id}/device-capabilities/household-snapshot",
            json=_snapshot_payload(catalog_device_id, runtime_status="online"),
        )
        second = client.put(
            f"/api/v1/projects/{project_id}/device-capabilities/household-snapshot",
            json=_snapshot_payload(catalog_device_id, runtime_status="offline"),
        )
        current = client.get(
            f"/api/v1/projects/{project_id}/device-capabilities/household-snapshot"
        )

        unreferenced_payload = _catalog_payload()
        unreferenced_payload["model"] = "E340-UNUSED"
        unreferenced_payload["product_name"] = "Unused evidence-backed device"
        unused = client.post(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog",
            json=unreferenced_payload,
        )
        assert unused.status_code == 201
        deleted = client.delete(
            f"/api/v1/projects/{project_id}/device-capabilities/catalog/"
            f"{unused.json()['catalog_device_id']}"
        )

        async def snapshot_statuses() -> list[tuple[int, str]]:
            async with application.state.database.session() as session:
                rows = await session.execute(
                    select(
                        HouseholdSnapshotModel.version,
                        HouseholdSnapshotModel.status,
                    )
                    .where(HouseholdSnapshotModel.project_id == project_id)
                    .order_by(HouseholdSnapshotModel.version.asc())
                )
                return [(int(version), str(status)) for version, status in rows]

        versions = asyncio.run(snapshot_statuses())
        project_deleted = client.delete(f"/api/v1/projects/{project_id}")

    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert second.status_code == 200
    assert second.json()["version"] == 2
    assert current.status_code == 200
    assert current.json()["version"] == 2
    assert current.json()["devices"][0]["runtime_status"] == "offline"
    assert versions == [(1, "superseded"), (2, "active")]
    assert deleted.status_code == 204
    assert project_deleted.status_code == 204
