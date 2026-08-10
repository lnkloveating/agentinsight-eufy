import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.infrastructure.database.models import (
    AgentArtifactModel,
    AgentRunModel,
    CollectionJobModel,
    EvidenceModel,
    SourceAssetModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'universal-recovery.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def test_user_agent_gap_accepts_processed_evidence_and_targets_only_affected_task(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    with TestClient(application) as client:
        created = client.post(
            "/api/v1/projects",
            json={
                "brief": {
                    "question": "What future package-safety product should eufy build?",
                    "category": "home security",
                    "target_user": "US households",
                    "region": "US",
                    "scenarios": ["front door package"],
                }
            },
        )
        assert created.status_code == 201
        project_id = created.json()["project_id"]

        async def seed() -> None:
            now = datetime.now(UTC)
            async with application.state.database.session() as session:
                run = AgentRunModel(
                    agent_run_id="run_user_gap",
                    project_id=project_id,
                    agent_type="user_research",
                    agent_name="user-research-agent",
                    task_id="task_user_research",
                    adapter_type="test",
                    attempt_number=1,
                    input_artifact_ids_json=[],
                    output_artifact_id="artifact_user_gap",
                    status="succeeded",
                    progress=100,
                    quality_score=65,
                    evidence_ids_json=[],
                    unknowns_json=[],
                    message="completed with a research gap",
                    started_at=now,
                    completed_at=now,
                )
                session.add(run)
                await session.flush()
                session.add(
                    AgentArtifactModel(
                        artifact_id="artifact_user_gap",
                        project_id=project_id,
                        agent_run_id=run.agent_run_id,
                        task_id="task_user_research",
                        artifact_type="user_research",
                        schema_version="1.0",
                        version=1,
                        status="partial",
                        payload_json={
                            "summary": "Available reviews do not establish frequency.",
                            "research_gaps": [
                                {
                                    "question": ("How often do delivered packages remain exposed?"),
                                    "reason": "No representative frequency sample is available.",
                                    "severity": "high",
                                    "recommended_source_types": ["authorized_user_interview"],
                                }
                            ],
                        },
                        evidence_ids_json=[],
                        contradictions_json=[],
                        unknowns_json=[],
                        quality_score=65,
                        errors_json=[],
                        input_artifact_ids_json=[],
                        content_hash="a" * 64,
                        created_at=now,
                    )
                )
                job = CollectionJobModel(
                    collection_job_id="job_authorized_interview",
                    project_id=project_id,
                    task_id="task_user_research",
                    source_url=None,
                    source_type="authorized_interview",
                    status="succeeded",
                    attempt_count=1,
                    result_json={"processed": True},
                    started_at=now,
                    completed_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(job)
                await session.flush()
                source = SourceAssetModel(
                    source_asset_id="source_authorized_interview",
                    project_id=project_id,
                    collection_job_id=job.collection_job_id,
                    kind="file",
                    status="ready",
                    display_name="Authorized package interview summary.pdf",
                    original_filename="package-interviews.pdf",
                    source_url=None,
                    normalized_source_url=None,
                    storage_key="test/authorized/package-interviews.pdf",
                    media_type="application/pdf",
                    media_category="document",
                    content_hash="b" * 64,
                    byte_size=1024,
                    authorization_basis="enterprise_authorized",
                    authorization_confirmed_at=now,
                    authorized_by="research-lead",
                    purpose="Fill the user research frequency gap.",
                    created_at=now,
                    updated_at=now,
                )
                session.add(source)
                await session.flush()
                session.add(
                    EvidenceModel(
                        evidence_id="ev_authorized_frequency",
                        project_id=project_id,
                        collection_job_id=job.collection_job_id,
                        source_url=None,
                        normalized_source_url=None,
                        source_domain=None,
                        source_asset_id=source.source_asset_id,
                        source_fragment_id=None,
                        source_locator_json={"kind": "page", "page": 3},
                        source_type="authorized_interview",
                        title="Authorized package exposure interview summary",
                        original_excerpt=(
                            "Interview participants repeatedly described packages remaining "
                            "outside while nobody was home."
                        ),
                        claim_type="user_opinion",
                        product=None,
                        region="US",
                        user_segment="household",
                        published_at=None,
                        collected_at=now,
                        status="partially_verified",
                        content_hash="c" * 64,
                        confidence=0.8,
                        authority_score=0.7,
                        recency_score=0.9,
                        diversity_score=0.5,
                    )
                )
                await session.commit()

        asyncio.run(seed())

        gaps = client.get(
            f"/api/v1/projects/{project_id}/agents/user_research/artifacts/artifact_user_gap/gaps"
        )
        assert gaps.status_code == 200
        gap = gaps.json()["items"][0]
        recovery_response = client.post(
            f"/api/v1/projects/{project_id}/agents/user_research/artifacts/"
            "artifact_user_gap/source-recovery",
            json={
                "gap_ids": [gap["gap_id"]],
                "requested_by": "research-lead",
                "reason": "Ask for the missing authorized user evidence.",
            },
        )
        assert recovery_response.status_code == 201
        recovery = recovery_response.json()
        field = recovery["requested_fields"][0]
        submitted = client.post(
            f"/api/v1/projects/{project_id}/source-recoveries/"
            f"{recovery['source_recovery_id']}/evidence-submissions",
            json={
                "request_id": "evidence-link-0001",
                "source_asset_id": "source_authorized_interview",
                "bindings": [
                    {
                        "field_id": field["field_id"],
                        "evidence_ids": ["ev_authorized_frequency"],
                    }
                ],
                "actor": "research-lead",
                "reason": "Bind the reviewed interview Evidence to the reported gap.",
            },
        )

    assert gap["severity"] == "high"
    assert gap["agent_type"] == "user_research"
    assert field["claim_type"] == "user_opinion"
    assert submitted.status_code == 201
    body = submitted.json()
    assert body["status"] == "resolved"
    assert body["submissions"][0]["source_asset_id"] == "source_authorized_interview"
    assert body["submissions"][0]["evidence_ids"] == ["ev_authorized_frequency"]
    assert body["resume_directive"]["mode"] == "targeted_retry"
    assert body["resume_directive"]["affected_task_ids"] == ["task_user_research"]
    assert body["resume_directive"]["affected_agent_types"] == ["user_research"]

    async def audit() -> tuple[int, list[str]]:
        async with application.state.database.session() as session:
            evidence_count = int(
                await session.scalar(select(func.count()).select_from(EvidenceModel)) or 0
            )
            events = await ProjectRepository(session).list_events(project_id, limit=100)
        return evidence_count, [event.event_type for event in events]

    evidence_count, event_types = asyncio.run(audit())
    assert evidence_count == 1
    assert "source_recovery_evidence_linked" in event_types
    assert "source_recovery_reassessed" in event_types
