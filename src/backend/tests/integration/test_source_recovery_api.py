import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infrastructure.database.models import EvidenceModel, SourceAssetModel
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'source-recovery.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def _project_and_failed_source(client: TestClient) -> tuple[str, str]:
    project = client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": "How should eufy smart doorbells evolve?",
                "category": "smart doorbell",
                "target_user": "US households",
                "region": "US",
                "scenarios": ["front door package"],
            }
        },
    )
    assert project.status_code == 201
    project_id = str(project.json()["project_id"])
    scoped = client.put(
        f"/api/v1/projects/{project_id}/source-requirements/scope",
        json={
            "target_products": [{"brand": "eufy", "model": "E340"}],
            "competitors": [{"brand": "Ring", "model": "D200"}],
            "dimensions": ["official_product"],
            "actor": "research-lead",
            "reason": "Compare exact doorbell models.",
        },
    )
    assert scoped.status_code == 200
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "https://ring.example/Ring-D200-official",
            "display_name": "Ring D200 official product page",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "Ring D200 official product research",
        },
    )
    assert registered.status_code == 201
    source_asset_id = str(registered.json()["source_asset"]["source_asset_id"])
    processing = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    assert processing.status_code == 200
    assert processing.json()["job"]["status"] == "blocked"
    assert processing.json()["job"]["error_code"] == "SOURCE_CONNECTOR_NOT_CONFIGURED"
    return project_id, source_asset_id


def test_failed_web_source_recovers_from_user_content_with_full_evidence_lineage(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    application.state.web_connector = None

    with TestClient(application) as client:
        project_id, failed_source_id = _project_and_failed_source(client)
        endpoint = f"/api/v1/projects/{project_id}/source-recoveries"
        created = client.post(
            endpoint,
            json={
                "source_asset_id": failed_source_id,
                "requirement_ids": [],
                "missing_questions": [],
                "affected_task_ids": ["task_competitor"],
                "affected_agent_types": [],
                "requested_by": "research-lead",
                "reason": "Automatic webpage processing produced no evidence.",
            },
        )
        assert created.status_code == 201
        recovery = created.json()
        recovery_id = str(recovery["source_recovery_id"])
        capability = next(
            item for item in recovery["requested_fields"] if item["field_key"] == "capability"
        )

        assert recovery["status"] == "waiting_for_user_input"
        assert recovery["reason_code"] == "connector_unavailable"
        assert recovery["failed_source_asset_id"] == failed_source_id
        assert recovery["affected_agent_types"] == ["competitor_research"]
        assert recovery["resume_directive"]["ready"] is False
        assert capability["required"] is True
        assert "Ring D200" in capability["question"]

        submitted = client.post(
            f"{endpoint}/{recovery_id}/submissions",
            json={
                "request_id": "request-0001",
                "answers": [
                    {
                        "field_id": capability["field_id"],
                        "value": "Supports package detection and person detection.",
                        "source_note": "Confirmed by an authorized product specialist.",
                    }
                ],
                "actor": "product-specialist",
                "authorization_basis": "enterprise_authorized",
                "authorization_confirmed": True,
                "accuracy_confirmed": True,
            },
        )
        replay = client.post(
            f"{endpoint}/{recovery_id}/submissions",
            json={
                "request_id": "request-0001",
                "answers": [
                    {
                        "field_id": capability["field_id"],
                        "value": "Supports package detection and person detection.",
                        "source_note": "Confirmed by an authorized product specialist.",
                    }
                ],
                "actor": "product-specialist",
                "authorization_basis": "enterprise_authorized",
                "authorization_confirmed": True,
                "accuracy_confirmed": True,
            },
        )
        listed = client.get(endpoint)

    assert submitted.status_code == 201
    body = submitted.json()
    assert body["status"] == "resolved"
    assert body["resume_directive"] == {
        "ready": True,
        "mode": "targeted_retry",
        "affected_task_ids": ["task_competitor"],
        "affected_agent_types": ["competitor_research"],
        "reason": "资料缺口已复评通过，只需恢复受影响的研究任务。",
    }
    assert len(body["submissions"]) == 1
    submission = body["submissions"][0]
    assert len(submission["evidence_ids"]) == 1
    assert replay.status_code == 201
    assert len(replay.json()["submissions"]) == 1
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    async def audit() -> tuple[SourceAssetModel, EvidenceModel, list[str]]:
        async with application.state.database.session() as session:
            asset = await session.get(SourceAssetModel, submission["source_asset_id"])
            evidence = await session.get(EvidenceModel, submission["evidence_ids"][0])
            events = await ProjectRepository(session).list_events(project_id, limit=100)
        assert asset is not None
        assert evidence is not None
        return asset, evidence, [event.event_type for event in events]

    asset, evidence, event_types = asyncio.run(audit())
    assert asset.kind == "user_input"
    assert asset.authorization_basis == "enterprise_authorized"
    assert evidence.source_asset_id == asset.source_asset_id
    assert evidence.source_type == "user_declaration"
    assert evidence.status == "partially_verified"
    assert evidence.source_url is None
    assert evidence.claim_type == "capability"
    assert evidence.product == "Ring D200"
    assert "source_recovery_requested" in event_types
    assert "source_recovery_submission_recorded" in event_types
    assert "source_recovery_reassessed" in event_types


def test_user_can_explicitly_proceed_with_gaps_without_creating_evidence(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    application.state.web_connector = None

    with TestClient(application) as client:
        project_id, failed_source_id = _project_and_failed_source(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/source-recoveries",
            json={
                "source_asset_id": failed_source_id,
                "requirement_ids": [],
                "missing_questions": [],
                "affected_task_ids": [],
                "affected_agent_types": [],
                "requested_by": "research-lead",
                "reason": "No accessible evidence was produced.",
            },
        )
        recovery_id = created.json()["source_recovery_id"]
        decided = client.post(
            f"/api/v1/projects/{project_id}/source-recoveries/{recovery_id}/decisions",
            json={
                "action": "proceed_with_gaps",
                "actor": "research-lead",
                "reason": "Continue but preserve the unknown competitor capability.",
            },
        )

    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "proceeding_with_gaps"
    assert body["submissions"] == []
    assert body["resume_directive"]["ready"] is True
    assert body["resume_directive"]["mode"] == "proceed_with_gaps"
    competitor_requirement = next(
        item
        for item in body["current_assessment"]["requirements"]
        if item["requirement_key"] == "material.official_product.competitor"
    )
    assert competitor_requirement["status"] == "blocked"


def test_generic_agent_gap_can_recover_without_competitor_source_requirements(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    application.state.web_connector = None

    with TestClient(application) as client:
        project = client.post(
            "/api/v1/projects",
            json={
                "brief": {
                    "question": "What future home security opportunity should eufy pursue?",
                    "category": "home security",
                    "target_user": "US households",
                    "region": "US",
                    "scenarios": ["front door"],
                }
            },
        )
        project_id = project.json()["project_id"]
        registered = client.post(
            f"/api/v1/projects/{project_id}/sources/links",
            json={
                "source_url": "https://research.example/authorized-study",
                "display_name": "Authorized household security study",
                "authorization_basis": "enterprise_authorized",
                "authorization_confirmed": True,
                "authorized_by": "research-team",
                "purpose": "Understand household package safety pain points",
            },
        )
        failed_source_id = registered.json()["source_asset"]["source_asset_id"]
        client.post(f"/api/v1/projects/{project_id}/sources/{failed_source_id}/processing")
        created = client.post(
            f"/api/v1/projects/{project_id}/source-recoveries",
            json={
                "source_asset_id": failed_source_id,
                "requirement_ids": [],
                "missing_questions": [
                    "What package-safety problem did households report most often?"
                ],
                "affected_task_ids": ["task_user_research"],
                "affected_agent_types": ["user_research"],
                "requested_by": "research-manager",
                "reason": "The user research source could not be parsed.",
            },
        )
        recovery = created.json()
        field = recovery["requested_fields"][0]
        submitted = client.post(
            f"/api/v1/projects/{project_id}/source-recoveries/"
            f"{recovery['source_recovery_id']}/submissions",
            json={
                "request_id": "generic-request-0001",
                "answers": [
                    {
                        "field_id": field["field_id"],
                        "value": "Residents worried that delivered packages remained exposed.",
                        "source_note": "Summary supplied by the authorized study owner.",
                    }
                ],
                "actor": "study-owner",
                "authorization_basis": "enterprise_authorized",
                "authorization_confirmed": True,
                "accuracy_confirmed": True,
            },
        )

    assert created.status_code == 201
    assert field["requirement_id"].startswith("requirement_source_gap_")
    assert field["claim_type"] == "fact"
    assert recovery["affected_agent_types"] == ["user_research"]
    assert submitted.status_code == 201
    assert submitted.json()["status"] == "resolved"
    assert submitted.json()["resume_directive"]["affected_task_ids"] == [
        "task_user_research"
    ]
