from datetime import UTC, datetime

import pytest

from app.agents.user_research.context import UserResearchEvidenceContextBuilder
from app.application.events import ProjectEventBroker
from app.application.evidence import EvidenceService
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import EvidenceClaimType, EvidenceIngest, EvidenceStatus


def _project() -> ProjectModel:
    now = datetime.now(UTC)
    return ProjectModel(
        project_id="proj_user_context",
        status="researching",
        current_stage="user_research",
        progress=20,
        brief_json={"question": "Research real user problems"},
        pending_decision_json=None,
        created_at=now,
        updated_at=now,
    )


def _evidence(
    url: str,
    excerpt: str,
    *,
    status: EvidenceStatus = EvidenceStatus.VERIFIED,
) -> EvidenceIngest:
    return EvidenceIngest(
        source_url=url,
        source_type="webpage",
        title="Authorized research source",
        original_excerpt=excerpt,
        claim_type=EvidenceClaimType.USER_OPINION,
        collected_at=datetime.now(UTC),
        status=status,
        confidence=0.9,
        authority_score=0.8,
        recency_score=0.7,
        diversity_score=0.6,
    )


@pytest.mark.asyncio
async def test_context_is_project_scoped_status_gated_diverse_and_bounded() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            session.add(_project())
            await session.commit()
            service = EvidenceService(
                EvidenceRepository(session),
                ProjectRepository(session),
                "trace_context",
                ProjectEventBroker(),
            )
            first = await service.ingest(
                "proj_user_context",
                _evidence("https://reviews.example/a", "A" * 900),
            )
            second = await service.ingest(
                "proj_user_context",
                _evidence("https://reviews.example/b", "B" * 900),
            )
            third = await service.ingest(
                "proj_user_context",
                _evidence("https://community.example/c", "C" * 900),
            )
            await service.ingest(
                "proj_user_context",
                _evidence(
                    "https://invalid.example/d",
                    "This invalid record must never reach the model.",
                    status=EvidenceStatus.INVALID,
                ),
            )

        context = await UserResearchEvidenceContextBuilder(
            database,
            max_items=2,
            max_excerpt_chars=500,
            max_total_chars=900,
        ).build("proj_user_context")

        assert context.available_evidence_count == 3
        assert context.included_evidence_count == 2
        assert context.omitted_evidence_count == 1
        selected_ids = {item.evidence_id for item in context.items}
        assert third.evidence.evidence_id in selected_ids
        assert selected_ids & {
            first.evidence.evidence_id,
            second.evidence.evidence_id,
        }
        assert sum(len(item.original_excerpt) for item in context.items) == 900
        assert len(context.context_hash) == 64
    finally:
        await database.dispose()
