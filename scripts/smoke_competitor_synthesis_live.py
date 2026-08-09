"""Run all three competitor specialists and synthesis against real configured models.

The Evidence below is an explicit ephemeral contract fixture. It verifies model routing,
structured output, A2A orchestration and evidence audit; it is never production research.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "src" / "backend"
ENVIRONMENT_PATH = BACKEND_ROOT / ".env"
sys.path.insert(0, str(BACKEND_ROOT))

from app.application.model_gateway import ModelCatalog
from app.application.runtime import AgentRuntimeGateway, RuntimeGatewayError
from app.core.config import Settings
from app.infrastructure.database import EvidenceModel, ProjectModel
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    AgentEvidence,
    AgentEvidenceContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)

PRODUCT = "Contract Fixture Doorbell"
PROJECT_ID = "project_live_competitor_synthesis"


def _brief() -> ResearchBrief:
    return ResearchBrief(
        question="Which product opportunity should be validated after competitor research?",
        category="smart doorbell",
        target_user="US households",
        region="US",
        scenarios=["front door package"],
        constraints=["contract fixture only", "evidence IDs required"],
    )


def _evidence_context() -> AgentEvidenceContext:
    collected_at = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)

    def evidence(
        evidence_id: str,
        claim_type: str,
        domain: str,
        excerpt: str,
        *,
        user_segment: str | None = None,
    ) -> AgentEvidence:
        return AgentEvidence(
            evidence_id=evidence_id,
            title=f"Ephemeral contract fixture {evidence_id}",
            original_excerpt=excerpt,
            claim_type=claim_type,
            status="verified",
            source_type="contract_fixture",
            source_url=f"https://{domain}/{evidence_id}",
            source_domain=domain,
            product=PRODUCT,
            region="US",
            user_segment=user_segment,
            collected_at=collected_at,
            confidence=0.9,
            authority_score=0.85,
            recency_score=0.9,
            diversity_score=0.8,
        )

    items = [
        evidence(
            "ev_live_official",
            "vendor_claim",
            "official-fixture.invalid",
            (
                "Contract Fixture Doorbell, model CF-1, documents package detection "
                "for the US region."
            ),
        ),
        evidence(
            "ev_live_price",
            "price_observation",
            "store-a-fixture.invalid",
            (
                "Contract Fixture Doorbell CF-1 has a regular observed price of "
                "USD 149.99 in the US Vendor Store."
            ),
        ),
        evidence(
            "ev_live_channel",
            "channel_availability",
            "store-b-fixture.invalid",
            "Contract Fixture Doorbell CF-1 is listed in stock by an authorized US retailer.",
        ),
        evidence(
            "ev_live_review_a",
            "user_opinion",
            "review-a-fixture.invalid",
            (
                "As a doorbell owner, I sometimes receive the package alert after "
                "the parcel has already been left outside."
            ),
            user_segment="doorbell owner",
        ),
        evidence(
            "ev_live_review_b",
            "user_opinion",
            "review-b-fixture.invalid",
            (
                "In my use of Contract Fixture Doorbell, package notifications can "
                "arrive late, delaying my response."
            ),
            user_segment="doorbell owner",
        ),
    ]
    return AgentEvidenceContext(
        items=items,
        available_evidence_count=len(items),
        included_evidence_count=len(items),
        omitted_evidence_count=0,
        context_hash="c" * 64,
    )


async def _persist_fixture(application: Any, model_id: str) -> None:
    now = datetime.now(UTC)
    context = _evidence_context()
    async with application.state.database.session() as session:
        session.add(
            ProjectModel(
                project_id=PROJECT_ID,
                status=ProjectStatus.RESEARCHING,
                current_stage="parallel_research",
                progress=30,
                brief_json=_brief().model_dump(mode="json"),
                model_selection_json={
                    "default_model_id": model_id,
                    "agent_overrides": {"competitor_research": model_id},
                },
                created_at=now,
                updated_at=now,
            )
        )
        for index, item in enumerate(context.items):
            session.add(
                EvidenceModel(
                    evidence_id=item.evidence_id,
                    project_id=PROJECT_ID,
                    collection_job_id=None,
                    source_url=item.source_url,
                    normalized_source_url=item.source_url,
                    source_domain=item.source_domain,
                    source_type=item.source_type,
                    title=item.title,
                    original_excerpt=item.original_excerpt,
                    claim_type=item.claim_type,
                    product=item.product,
                    region=item.region,
                    user_segment=item.user_segment,
                    published_at=None,
                    collected_at=item.collected_at or now,
                    status=item.status,
                    content_hash=f"{index + 1:064x}",
                    confidence=item.confidence,
                    authority_score=item.authority_score,
                    recency_score=item.recency_score,
                    diversity_score=item.diversity_score,
                )
            )
        await session.commit()


async def _run(application: Any, model_id: str) -> dict[str, Any]:
    await _persist_fixture(application, model_id)
    task = ResearchTask(
        task_id="task_live_competitor_synthesis",
        project_id=PROJECT_ID,
        agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
        goal="Run the three competitor specialists and evidence-bounded synthesis.",
        scope={"target_product": PRODUCT},
        evidence_rules=EvidenceRules(
            citation_required=True, minimum_independent_domains=2
        ),
        budget=ResearchBudget(max_pages=20, max_iterations=1, deadline_seconds=600),
    )
    try:
        artifact = await AgentRuntimeGateway(
            application.state.database,
            application.state.agent_registry,
            application.state.event_broker,
            "trace_live_competitor_synthesis",
        ).execute(
            task,
            AgentContext(
                project_id=PROJECT_ID,
                brief=_brief(),
                iteration=0,
                evidence_context=_evidence_context(),
            ),
        )
    except RuntimeGatewayError as exc:
        raise RuntimeError(
            f"competitor synthesis live smoke failed: {exc.code}; details={exc.details}"
        ) from exc
    async with application.state.database.session() as session:
        runs = await ProjectRepository(session).list_agent_runs(PROJECT_ID)
        run = next(item for item in runs if item.task_id == task.task_id)
        model_calls = await ModelCallRepository(session).list_for_run(run.agent_run_id)
    payload = artifact.payload
    return {
        "model_id": model_id,
        "artifact_status": artifact.status,
        "schema_name": payload.get("schema_name"),
        "synthesis_status": payload.get("synthesis_status"),
        "evidence_audit_status": payload.get("evidence_audit", {}).get("status"),
        "specialist_output_count": len(payload.get("specialist_outputs", [])),
        "product_profile_count": len(payload.get("product_profiles", [])),
        "opportunity_signal_count": len(payload.get("opportunity_signals", [])),
        "cited_evidence_count": len(artifact.evidence_ids),
        "model_call_count": len(model_calls),
        "model_call_statuses": [call.status for call in model_calls],
        "prompt_keys": [call.prompt_key for call in model_calls],
    }


def run_live_smoke(model_id: str) -> dict[str, Any]:
    if not ENVIRONMENT_PATH.is_file():
        raise RuntimeError("src/backend/.env is required for the live smoke test")
    base_settings = Settings(_env_file=ENVIRONMENT_PATH)
    ModelCatalog.from_json(
        base_settings.model_catalog_json,
        default_model_id=base_settings.default_model_id,
    ).require_enabled(model_id)
    with TemporaryDirectory(prefix="agentinsight-competitor-synthesis-") as temp_root:
        temp_path = Path(temp_root)
        settings = base_settings.model_copy(
            update={
                "app_env": "smoke-test",
                "database_url": f"sqlite+aiosqlite:///{temp_path / 'smoke.db'}",
                "auto_create_schema": True,
                "model_credentials_env_file": str(ENVIRONMENT_PATH),
                "source_storage_root": str(temp_path / "sources"),
                "source_processing_workspace_root": str(temp_path / "processing"),
            }
        )
        application = create_app(settings)
        with TestClient(application):
            return asyncio.run(_run(application, model_id))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description=(
            "Run the full competitor A2A and synthesis path against one configured real model."
        )
    )
    parser.add_argument("--model", default="anker:glm-5.2")
    args = parser.parse_args()
    print(
        json.dumps(
            run_live_smoke(args.model), ensure_ascii=False, indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
