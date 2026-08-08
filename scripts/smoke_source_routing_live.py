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
from smoke_official_product_live import _create_and_approve_project
from smoke_user_research_live import DEFAULT_URLS, _expect


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
    with TemporaryDirectory(prefix="agentinsight-source-routing-") as temp_root:
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
                for source_url in urls:
                    project_id = _create_and_approve_project(client, model_id)
                    registered = _expect(
                        client.post(
                            f"/api/v1/projects/{project_id}/sources/links",
                            json={
                                "source_url": source_url,
                                "display_name": "Authorized product research page",
                                "authorization_basis": "publicly_available",
                                "authorization_confirmed": True,
                                "authorized_by": "backend-smoke-test",
                                "purpose": "Automatically classify this research source",
                            },
                        ),
                        201,
                        "register routing source",
                    )
                    source_asset_id = str(registered["source_asset"]["source_asset_id"])
                    processed = _expect(
                        client.post(
                            f"/api/v1/projects/{project_id}/sources/"
                            f"{source_asset_id}/processing"
                        ),
                        200,
                        "process routing source",
                    )
                    if processed["job"]["status"] != "succeeded":
                        raise RuntimeError("source routing webpage processing failed")
                    routing = _expect(
                        client.post(
                            f"/api/v1/projects/{project_id}/sources/"
                            f"{source_asset_id}/routing/analyze",
                            json={"use_model": True, "force": True},
                        ),
                        200,
                        "analyze source routing",
                    )
                    suggested_routes = {
                        str(item["route"]) for item in routing["suggestions"]
                    }
                    if "official_product" not in suggested_routes:
                        raise RuntimeError(
                            "live routing did not identify the authorized product page"
                        )
                    if routing["model_call_id"] is None:
                        raise RuntimeError(
                            "live routing did not execute the selected organizer model"
                        )
                    evidence_page = _expect(
                        client.get(f"/api/v1/projects/{project_id}/evidence"),
                        200,
                        "verify routing did not create evidence",
                    )
                    results.append(
                        {
                            "model_id": model_id,
                            "routing_status": routing["status"],
                            "routing_method": routing["method"],
                            "suggested_routes": sorted(suggested_routes),
                            "suggestion_count": len(routing["suggestions"]),
                            "confirmed_route_count": len(routing["confirmed_routes"]),
                            "model_call_recorded": True,
                            "fragment_count": processed["parsed_artifact"][
                                "fragment_count"
                            ],
                            "evidence_created_by_routing": len(evidence_page["items"]),
                        }
                    )
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Run a live authorized webpage through multi-label source routing."
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--url", action="append", dest="urls")
    args = parser.parse_args()
    results = run_live_smoke(
        args.models or ["anker:glm-5.2", "anker:deepseek-v4-pro"],
        args.urls or [DEFAULT_URLS[0]],
    )
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
