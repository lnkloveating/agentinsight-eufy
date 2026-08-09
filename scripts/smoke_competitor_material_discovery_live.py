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

from app.core.config import Settings
from app.main import create_app
from smoke_user_research_live import _expect


def run_live_smoke() -> dict[str, Any]:
    if not ENVIRONMENT_PATH.is_file():
        raise RuntimeError("src/backend/.env is required for the live smoke test")
    base_settings = Settings(_env_file=ENVIRONMENT_PATH)
    with TemporaryDirectory(prefix="agentinsight-material-discovery-") as temp_root:
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
            project = _expect(
                client.post(
                    "/api/v1/projects",
                    json={
                        "brief": {
                            "question": "What can eufy learn from competing package doorbells?",
                            "category": "smart doorbell",
                            "target_user": "US households",
                            "region": "US",
                            "scenarios": ["front door package monitoring"],
                        }
                    },
                ),
                201,
                "create material discovery project",
            )
            project_id = str(project["project_id"])
            _expect(
                client.put(
                    f"/api/v1/projects/{project_id}/source-requirements/scope",
                    json={
                        "target_products": [{"brand": "eufy", "model": "E340"}],
                        "competitors": [
                            {"brand": "Ring", "model": "Battery Doorbell Pro"}
                        ],
                        "dimensions": [
                            "official_product",
                            "price_channel",
                            "user_review",
                        ],
                        "actor": "backend-smoke-test",
                        "reason": "Confirm exact products for live material discovery.",
                    },
                ),
                200,
                "set exact competitor material scope",
            )
            discovery = _expect(
                client.post(
                    f"/api/v1/projects/{project_id}/competitor-material-discoveries",
                    json={
                        "products": [
                            {
                                "product_role": "competitor",
                                "product": {
                                    "brand": "Ring",
                                    "model": "Battery Doorbell Pro",
                                },
                            }
                        ],
                        "dimensions": [
                            "official_product",
                            "price_channel",
                            "user_review",
                        ],
                        "provider_id": "tavily",
                        "max_results_per_query": 3,
                        "requested_by": "backend-smoke-test",
                        "purpose": "Find real public research candidates for each dimension.",
                    },
                ),
                201,
                "run live competitor material discovery",
            )
            if discovery["status"] != "completed":
                raise RuntimeError(
                    f"material discovery did not complete: {discovery['status']}"
                )
            empty_dimensions = [
                item["dimension"]
                for item in discovery["items"]
                if not item["search_run"]["candidates"]
            ]
            if empty_dimensions:
                raise RuntimeError(
                    f"live search returned no candidates for: {empty_dimensions}"
                )
            sources = _expect(
                client.get(f"/api/v1/projects/{project_id}/sources"),
                200,
                "verify candidate-only source boundary",
            )
            evidence = _expect(
                client.get(f"/api/v1/projects/{project_id}/evidence"),
                200,
                "verify candidate-only evidence boundary",
            )
            if sources["total"] != 0 or evidence["items"]:
                raise RuntimeError("discovery crossed the Source or Evidence human gate")
            return {
                "project_id": project_id,
                "material_discovery_id": discovery["material_discovery_id"],
                "status": discovery["status"],
                "query_count": discovery["item_count"],
                "candidate_count": discovery["candidate_count"],
                "dimensions": {
                    item["dimension"]: item["search_run"]["result_count"]
                    for item in discovery["items"]
                },
                "source_asset_count_before_gate": sources["total"],
                "evidence_count_before_gate": len(evidence["items"]),
            }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run live Tavily competitor-material discovery without crossing the Gate."
    )
    parser.parse_args()
    print(json.dumps(run_live_smoke(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
