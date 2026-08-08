from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "src" / "backend"
ENVIRONMENT_PATH = BACKEND_ROOT / ".env"
sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.competitor import OfficialProductEvidenceContextBuilder
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
from smoke_user_research_live import DEFAULT_URLS, _expect, _process_page


def _create_and_approve_project(client: TestClient, model_id: str) -> str:
    project = _expect(
        client.post(
            "/api/v1/projects",
            json={
                "brief": {
                    "question": (
                        "What official capabilities and limitations are supported by "
                        "the provided eufy product pages?"
                    ),
                    "category": "eufy home security",
                    "target_user": "North American households",
                    "region": "US",
                    "scenarios": ["front door package", "local home security"],
                    "constraints": ["evidence only", "no inferred specifications"],
                    "focus_dimensions": [
                        "capabilities",
                        "specifications",
                        "limitations",
                    ],
                },
                "model_selection": {
                    "default_model_id": model_id,
                    "agent_overrides": {"competitor_research": model_id},
                },
            },
        ),
        201,
        "create project",
    )
    project_id = str(project["project_id"])
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/decisions",
            json={
                "decision_id": project["pending_decision"]["decision_id"],
                "action": "approve",
                "reason": "Official source scope is explicit.",
                "actor": "backend-smoke-test",
            },
        ),
        202,
        "approve project",
    )
    return project_id


async def _run_official_specialist(
    application: Any,
    project_id: str,
) -> dict[str, Any]:
    evidence_context = await OfficialProductEvidenceContextBuilder(
        application.state.database,
        max_items=40,
        max_excerpt_chars=3_000,
        max_total_chars=60_000,
    ).build(project_id)
    task = ResearchTask(
        task_id="task_live_official_product",
        project_id=project_id,
        agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
        goal="Extract evidence-backed official product intelligence.",
        scope={"target_product": "eufy home security"},
        evidence_rules=EvidenceRules(
            citation_required=True,
            minimum_independent_domains=2,
        ),
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
            "trace_live_official_product",
        ).execute(
            task,
            AgentContext(
                project_id=project_id,
                brief=ResearchBrief(
                    question=(
                        "What official capabilities and limitations are supported by the "
                        "provided eufy product pages?"
                    ),
                    category="eufy home security",
                    target_user="North American households",
                    region="US",
                    scenarios=["front door package", "local home security"],
                ),
                iteration=0,
                evidence_context=evidence_context,
            ),
        )
    except RuntimeGatewayError as exc:
        async with application.state.database.session() as session:
            failed_tasks = await A2ATaskRepository(session).list_for_parent(
                project_id, task.task_id
            )
            runs = await ProjectRepository(session).list_agent_runs(project_id)
            competitor_run = next(run for run in runs if run.task_id == task.task_id)
            model_calls = await ModelCallRepository(session).list_for_run(
                competitor_run.agent_run_id
            )
        failures = [
            f"{item.specialist_type}:{item.error_code}"
            for item in failed_tasks
            if item.error_code is not None
        ]
        call_failures = [
            f"attempt={call.attempt_number},status={call.status},code={call.error_code}"
            for call in model_calls
        ]
        raise RuntimeError(
            "official specialist smoke failed: "
            + ", ".join(failures)
            + "; model_calls="
            + "|".join(call_failures)
        ) from exc
    async with application.state.database.session() as session:
        tasks = await A2ATaskRepository(session).list_for_parent(
            project_id, task.task_id
        )
    official_task = next(
        item for item in tasks if item.specialist_type == "official_product"
    )
    output = official_task.output_json or {}
    payload = output.get("structured_payload", {})
    return {
        "parent_artifact_status": artifact.status,
        "official_task_status": official_task.status,
        "evidence_context_count": evidence_context.included_evidence_count,
        "official_evidence_count": len(output.get("evidence_ids", [])),
        "official_finding_count": len(output.get("findings", [])),
        "product_record_count": len(payload.get("products", [])),
        "schema_name": payload.get("schema_name"),
        "quality_score": output.get("quality_score"),
        "attempt_count": official_task.attempt_count,
    }


def run_live_smoke(model_ids: list[str], urls: list[str]) -> list[dict[str, Any]]:
    if not ENVIRONMENT_PATH.is_file():
        raise RuntimeError("src/backend/.env is required for the live smoke test")
    base_settings = Settings(_env_file=ENVIRONMENT_PATH)
    catalog = ModelCatalog.from_json(
        base_settings.model_catalog_json,
        default_model_id=base_settings.default_model_id,
    )
    for model_id in model_ids:
        catalog.require_enabled(model_id)

    results: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="agentinsight-official-product-") as temp_root:
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
                project_id = _create_and_approve_project(client, model_id)
                pages: list[dict[str, Any]] = []
                promoted_evidence_ids: list[str] = []
                for source_url in urls:
                    page, evidence_ids = _process_page(
                        client,
                        project_id,
                        source_url,
                        claim_type="vendor_claim",
                    )
                    source_asset_id = str(page["source_asset_id"])
                    _expect(
                        client.post(
                            f"/api/v1/projects/{project_id}/sources/"
                            f"{source_asset_id}/routing/analyze",
                            json={"use_model": False},
                        ),
                        200,
                        "analyze official source routing",
                    )
                    _expect(
                        client.post(
                            f"/api/v1/projects/{project_id}/sources/"
                            f"{source_asset_id}/routing/decision",
                            json={
                                "action": "confirm",
                                "selections": [
                                    {
                                        "route": "official_product",
                                        "claim_types": ["vendor_claim"],
                                    }
                                ],
                                "actor": "backend-smoke-test",
                                "reason": "The supplied URL is an authorized official product page.",
                            },
                        ),
                        200,
                        "confirm official source routing",
                    )
                    pages.append(page)
                    promoted_evidence_ids.extend(evidence_ids)
                result = asyncio.run(_run_official_specialist(application, project_id))
                result.update(
                    {
                        "model_id": model_id,
                        "page_count": len(pages),
                        "parsed_fragment_count": sum(
                            int(page["fragment_count"]) for page in pages
                        ),
                        "promoted_evidence_count": len(set(promoted_evidence_ids)),
                    }
                )
                results.append(result)
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description=(
            "Run live authorized webpages through the official-product A2A specialist."
        )
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--url", action="append", dest="urls")
    args = parser.parse_args()
    results = run_live_smoke(
        args.models or ["anker:glm-5.2", "anker:deepseek-v4-pro"],
        args.urls or list(DEFAULT_URLS),
    )
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
