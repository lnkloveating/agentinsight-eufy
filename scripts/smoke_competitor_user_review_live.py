from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "src" / "backend"
ENVIRONMENT_PATH = BACKEND_ROOT / ".env"
sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.competitor import UserReviewEvidenceContextBuilder
from app.application.model_gateway import ModelCatalog
from app.application.runtime import AgentRuntimeGateway, RuntimeGatewayError
from app.core.config import Settings
from app.infrastructure.database.a2a_repository import A2ATaskRepository
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.main import create_app
from app.schemas.project import ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)
from smoke_user_research_live import _expect

DEFAULT_REVIEW_URL = (
    "https://www.homesandgardens.com/solved/eufy-e340-video-doorbell-review"
)
DEFAULT_PRODUCT = "eufy Security Video Doorbell E340"
FIRST_PERSON_PATTERN = re.compile(r"\b(?:I|I'm|I've|my|me)\b", re.IGNORECASE)
REVIEW_TERMS = (
    "delay",
    "notification",
    "alert",
    "package",
    "doorbell",
    "live view",
    "audio",
    "video",
    "battery",
    "install",
    "app",
)


def _create_and_approve_project(client: TestClient, model_id: str, product: str) -> str:
    project = _expect(
        client.post(
            "/api/v1/projects",
            json={
                "brief": {
                    "question": f"What user experiences are supported for {product}?",
                    "category": "smart doorbell",
                    "target_user": "doorbell owners",
                    "region": "US",
                    "scenarios": ["front door package", "answering a visitor"],
                    "constraints": ["evidence only", "do not infer prevalence"],
                    "focus_dimensions": ["user opinions", "events", "sample limitations"],
                },
                "model_selection": {
                    "default_model_id": model_id,
                    "agent_overrides": {"competitor_research": model_id},
                },
            },
        ),
        201,
        "create competitor user-review project",
    )
    project_id = str(project["project_id"])
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/decisions",
            json={
                "decision_id": project["pending_decision"]["decision_id"],
                "action": "approve",
                "reason": "The exact product and public first-person review are authorized.",
                "actor": "backend-smoke-test",
            },
        ),
        202,
        "approve competitor user-review project",
    )
    return project_id


def _list_fragments(client: TestClient, project_id: str, source_asset_id: str) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = _expect(
            client.get(
                f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments",
                params={"cursor": cursor} if cursor else None,
            ),
            200,
            "list review fragments",
        )
        fragments.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return fragments


def _select_first_person_review(fragments: list[dict[str, Any]]) -> dict[str, Any]:
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for fragment in fragments:
        excerpt = str(fragment.get("original_excerpt", ""))
        if not FIRST_PERSON_PATTERN.search(excerpt):
            continue
        term_count = sum(term in excerpt.casefold() for term in REVIEW_TERMS)
        if term_count == 0:
            continue
        ranked.append((term_count, min(len(excerpt), 2_000), fragment))
    if not ranked:
        raise RuntimeError(
            "authorized page contained no first-person product-experience fragment; "
            "the smoke test refuses to classify marketing text as user_opinion"
        )
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def _process_review_page(
    client: TestClient, project_id: str, source_url: str, product: str
) -> dict[str, Any]:
    registered = _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/links",
            json={
                "source_url": source_url,
                "display_name": f"Authorized first-person review of {product}",
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "authorized_by": "backend-smoke-test",
                "purpose": "First-person user review and product experience research",
            },
        ),
        201,
        "register review webpage",
    )
    source_asset_id = str(registered["source_asset"]["source_asset_id"])
    processing = _expect(
        client.post(f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"),
        200,
        "process review webpage",
    )
    if processing["job"]["status"] != "succeeded":
        raise RuntimeError(
            "review webpage processing failed: "
            f"{processing['job'].get('error_code')} {processing['job'].get('error_message')}"
        )
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/analyze",
            json={"use_model": False},
        ),
        200,
        "analyze review routing",
    )
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/decision",
            json={
                "action": "confirm",
                "selections": [
                    {"route": "user_review", "claim_types": ["user_opinion"]}
                ],
                "actor": "backend-smoke-test",
                "reason": "Reviewed excerpt is a first-person product-use account.",
            },
        ),
        200,
        "confirm review routing",
    )
    fragments = _list_fragments(client, project_id, source_asset_id)
    selected = _select_first_person_review(fragments)
    promoted = _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments/"
            f"{selected['source_fragment_id']}/evidence",
            json={
                "claim_type": "user_opinion",
                "product": product,
                "region": None,
                "user_segment": "professional product reviewer",
                "confidence": 0.8,
                "authority_score": 0.75,
                "recency_score": 0.9,
                "diversity_score": 0.3,
            },
        ),
        201,
        "promote reviewed user-opinion fragment",
    )
    return {
        "source_asset_id": source_asset_id,
        "fragment_count": len(fragments),
        "evidence_id": str(promoted["evidence"]["evidence_id"]),
        "parser_id": processing["parsed_artifact"]["parser_id"],
    }


async def _run_specialist(application: Any, project_id: str, product: str) -> dict[str, Any]:
    evidence_context = await UserReviewEvidenceContextBuilder(
        application.state.database,
        max_items=80,
        max_excerpt_chars=3_000,
        max_total_chars=100_000,
    ).build(project_id)
    task = ResearchTask(
        task_id="task_live_competitor_user_review",
        project_id=project_id,
        agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
        goal="Extract evidence-backed competitor user-review intelligence.",
        scope={"target_product": product},
        evidence_rules=EvidenceRules(citation_required=True, minimum_independent_domains=1),
        budget=ResearchBudget(
            max_pages=evidence_context.included_evidence_count,
            max_iterations=1,
            deadline_seconds=300,
        ),
    )
    try:
        artifact = await AgentRuntimeGateway(
            application.state.database,
            application.state.agent_registry,
            application.state.event_broker,
            "trace_live_competitor_user_review",
        ).execute(
            task,
            AgentContext(
                project_id=project_id,
                brief=ResearchBrief(
                    question=f"What user experiences are supported for {product}?",
                    category="smart doorbell",
                    target_user="doorbell owners",
                    region="US",
                    scenarios=["front door package", "answering a visitor"],
                ),
                iteration=0,
                evidence_context=evidence_context,
            ),
        )
    except RuntimeGatewayError as exc:
        raise RuntimeError(f"competitor user-review specialist failed: {exc.code}") from exc
    async with application.state.database.session() as session:
        tasks = await A2ATaskRepository(session).list_for_parent(project_id, task.task_id)
        runs = await ProjectRepository(session).list_agent_runs(project_id)
        run = next(item for item in runs if item.task_id == task.task_id)
        model_calls = await ModelCallRepository(session).list_for_run(run.agent_run_id)
    review_task = next(item for item in tasks if item.specialist_type == "user_review")
    output = review_task.output_json or {}
    payload = output.get("structured_payload", {})
    coverage = payload.get("evidence_coverage", {})
    return {
        "parent_artifact_status": artifact.status,
        "review_task_status": review_task.status,
        "evidence_context_count": evidence_context.included_evidence_count,
        "cited_evidence_count": len(output.get("evidence_ids", [])),
        "review_theme_count": len(payload.get("review_themes", [])),
        "single_report_theme_count": coverage.get("single_report_theme_count"),
        "repeated_theme_count": coverage.get("repeated_theme_count"),
        "sample_limitation_count": len(payload.get("sample_limitations", [])),
        "schema_name": payload.get("schema_name"),
        "quality_score": output.get("quality_score"),
        "model_call_count": len(model_calls),
        "model_call_statuses": [item.status for item in model_calls],
    }


def run_live_smoke(
    model_ids: list[str], source_url: str, product: str
) -> list[dict[str, Any]]:
    if not ENVIRONMENT_PATH.is_file():
        raise RuntimeError("src/backend/.env is required for the live smoke test")
    base_settings = Settings(_env_file=ENVIRONMENT_PATH)
    catalog = ModelCatalog.from_json(
        base_settings.model_catalog_json, default_model_id=base_settings.default_model_id
    )
    for model_id in model_ids:
        catalog.require_enabled(model_id)

    results: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="agentinsight-competitor-user-review-") as temp_root:
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
        with TestClient(application) as client:
            for model_id in model_ids:
                project_id = _create_and_approve_project(client, model_id, product)
                page = _process_review_page(client, project_id, source_url, product)
                result = asyncio.run(_run_specialist(application, project_id, product))
                result.update(
                    {
                        "model_id": model_id,
                        "fragment_count": page["fragment_count"],
                        "promoted_evidence_count": 1,
                        "parser_id": page["parser_id"],
                    }
                )
                results.append(result)
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Run a real reviewed webpage through the competitor user-review A2A expert."
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--url", default=DEFAULT_REVIEW_URL)
    parser.add_argument("--product", default=DEFAULT_PRODUCT)
    args = parser.parse_args()
    result = run_live_smoke(
        args.models or ["anker:glm-5.2", "anker:deepseek-v4-pro"],
        args.url,
        args.product,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
