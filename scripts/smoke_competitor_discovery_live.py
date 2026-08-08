from __future__ import annotations

import argparse
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

from app.application.model_gateway import ModelCatalog
from app.core.config import Settings
from app.main import create_app
from smoke_user_research_live import _expect


def _create_project(client: TestClient, model_id: str) -> str:
    project = _expect(
        client.post(
            "/api/v1/projects",
            json={
                "brief": {
                    "question": "Which exact smart doorbells compete with eufy E340?",
                    "category": "smart doorbell",
                    "target_user": "North American households",
                    "region": "US",
                    "scenarios": ["front door package monitoring"],
                    "constraints": ["candidate discovery only", "no unsupported facts"],
                },
                "model_selection": {
                    "default_model_id": model_id,
                    "agent_overrides": {"competitor_research": model_id},
                },
            },
        ),
        201,
        "create competitor discovery project",
    )
    project_id = str(project["project_id"])
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/decisions",
            json={
                "decision_id": project["pending_decision"]["decision_id"],
                "action": "approve",
                "reason": "The target category and product are explicit.",
                "actor": "backend-smoke-test",
            },
        ),
        202,
        "approve competitor discovery project",
    )
    _expect(
        client.put(
            f"/api/v1/projects/{project_id}/source-requirements/scope",
            json={
                "target_products": [{"brand": "eufy", "model": "E340"}],
                "competitors": [],
                "dimensions": ["official_product", "price_channel", "user_review"],
                "actor": "backend-smoke-test",
                "reason": "Confirm the exact target before competitor discovery.",
            },
        ),
        200,
        "set competitor discovery scope",
    )
    return project_id


def run_live_smoke(model_ids: list[str]) -> list[dict[str, Any]]:
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
    with TemporaryDirectory(prefix="agentinsight-competitor-discovery-") as temp_root:
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
                project_id = _create_project(client, model_id)
                search = _expect(
                    client.post(
                        f"/api/v1/projects/{project_id}/source-discovery/searches",
                        json={
                            "query": (
                                "eufy E340 direct competitors exact smart video doorbell "
                                "models Ring Google Nest Arlo official product"
                            ),
                            "intent": "competitor_candidate",
                            "provider_id": "tavily",
                            "max_results": 5,
                            "include_domains": [],
                            "exclude_domains": [],
                            "requested_by": "backend-smoke-test",
                            "purpose": "Find exact competitor candidates for human review.",
                        },
                    ),
                    201,
                    "run live competitor search",
                )
                if search["status"] != "succeeded" or not search["candidates"]:
                    raise RuntimeError(
                        "live competitor search did not return successful candidates: "
                        f"status={search['status']} error_code={search['error_code']}"
                    )
                artifact = _expect(
                    client.post(
                        f"/api/v1/projects/{project_id}/agents/competitor-discovery",
                        json={
                            "search_discovery_run_ids": [
                                search["search_discovery_run_id"]
                            ],
                            "minimum_candidates": 1,
                        },
                    ),
                    200,
                    "run live competitor discovery agent",
                )
                requirements = _expect(
                    client.get(f"/api/v1/projects/{project_id}/source-requirements"),
                    200,
                    "verify candidate gate isolation",
                )
                runs = _expect(
                    client.get(f"/api/v1/projects/{project_id}/agents"),
                    200,
                    "read competitor discovery audit",
                )
                matching_runs = [
                    item
                    for item in runs
                    if item["task_id"] == "task_competitor_discovery"
                ]
                if not matching_runs or matching_runs[-1]["model_id"] != model_id:
                    raise RuntimeError("competitor discovery model audit is missing")
                if artifact["gate_status"] != "pending":
                    raise RuntimeError("candidate artifact bypassed the human Gate")
                if requirements["scope"]["competitors"]:
                    raise RuntimeError("candidate artifact changed scope before approval")
                results.append(
                    {
                        "model_id": model_id,
                        "search_status": search["status"],
                        "search_candidate_count": len(search["candidates"]),
                        "artifact_status": artifact["status"],
                        "proposal_count": len(artifact["proposals"]),
                        "excluded_group_count": len(artifact["excluded_candidates"]),
                        "gate_status": artifact["gate_status"],
                        "scope_competitor_count_before_gate": 0,
                        "evidence_ids_created": 0,
                        "model_call_recorded": True,
                    }
                )
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Run Tavily candidates through the live competitor discovery Agent."
    )
    parser.add_argument("--model", action="append", dest="models")
    args = parser.parse_args()
    results = run_live_smoke(args.models or ["anker:glm-5.2"])
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
