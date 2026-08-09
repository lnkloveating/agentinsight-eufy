from __future__ import annotations

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
    with TemporaryDirectory(prefix="agentinsight-fragment-evidence-") as temp_root:
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
                            "question": "What can eufy learn from its current doorbell evidence?",
                            "category": "smart doorbell",
                            "target_user": "US households",
                            "region": "US",
                            "scenarios": ["front door package monitoring"],
                        }
                    },
                ),
                201,
                "create live Fragment Evidence project",
            )
            project_id = str(project["project_id"])
            _expect(
                client.put(
                    f"/api/v1/projects/{project_id}/source-requirements/scope",
                    json={
                        "target_products": [{"brand": "eufy", "model": "E340"}],
                        "competitors": [],
                        "dimensions": ["official_product"],
                        "actor": "backend-smoke-test",
                        "reason": "Confirm the exact target product and evidence dimension.",
                    },
                ),
                200,
                "set live evidence scope",
            )
            discovery = _expect(
                client.post(
                    f"/api/v1/projects/{project_id}/competitor-material-discoveries",
                    json={
                        "products": [
                            {
                                "product_role": "target",
                                "product": {"brand": "eufy", "model": "E340"},
                            }
                        ],
                        "dimensions": ["official_product"],
                        "provider_id": "tavily",
                        "max_results_per_query": 8,
                        "requested_by": "backend-smoke-test",
                        "purpose": "Find the real public eufy E340 official product page.",
                    },
                ),
                201,
                "discover real eufy E340 material",
            )
            candidates = discovery["items"][0]["search_run"]["candidates"]
            candidate = next(
                (
                    item
                    for item in candidates
                    if item["source_domain"].endswith("eufy.com")
                    and "/products/" in item["normalized_source_url"]
                ),
                None,
            )
            if candidate is None:
                raise RuntimeError("Tavily returned no public eufy product-page candidate")
            decision = _expect(
                client.post(
                    f"/api/v1/projects/{project_id}/competitor-material-discoveries/"
                    f"{discovery['material_discovery_id']}/decision",
                    json={
                        "action": "confirm",
                        "selected_candidate_ids": [candidate["candidate_id"]],
                        "authorization_basis": "publicly_available",
                        "authorization_confirmed": True,
                        "actor": "backend-smoke-test",
                        "reason": "Authorize the real public product page for this smoke test.",
                    },
                ),
                201,
                "authorize and process the real public product page",
            )
            source = decision["decision"]["selections"][0]["source_asset"]
            source_asset_id = source["source_asset_id"]
            processing = _expect(
                client.get(
                    f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
                ),
                200,
                "read real webpage processing result",
            )
            if processing["job"]["status"] != "succeeded":
                raise RuntimeError(
                    "real webpage did not produce verified fragments: "
                    f"{processing['job']['error_code']}"
                )
            fragments = _expect(
                client.get(
                    f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
                ),
                200,
                "list real verified webpage fragments",
            )
            selected_fragment_ids = [
                item["source_fragment_id"] for item in fragments["items"][:50]
            ]
            if not selected_fragment_ids:
                raise RuntimeError("real webpage processing returned no source fragments")
            routing = _expect(
                client.get(
                    f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing"
                ),
                200,
                "read real webpage routing",
            )
            if routing["status"] != "confirmed":
                official = next(
                    (
                        item
                        for item in routing["suggestions"]
                        if item["route"] == "official_product"
                    ),
                    None,
                )
                if official is None:
                    raise RuntimeError("real webpage has no official-product routing suggestion")
                routing = _expect(
                    client.post(
                        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/"
                        "routing/decision",
                        json={
                            "action": "confirm",
                            "selections": [
                                {
                                    "route": "official_product",
                                    "claim_types": official["claim_types"],
                                }
                            ],
                            "actor": "backend-smoke-test",
                            "reason": "Confirm the observed official product-page routing.",
                        },
                    ),
                    200,
                    "confirm real webpage routing",
                )
            batch = _expect(
                client.post(
                    f"/api/v1/projects/{project_id}/fragment-evidence-batches",
                    json={
                        "source_asset_ids": [source_asset_id],
                        "source_fragment_ids": selected_fragment_ids,
                        "requested_by": "backend-smoke-test",
                        "purpose": "Prepare real verified webpage fragments for Evidence review.",
                    },
                ),
                201,
                "create real Fragment Evidence Draft batch",
            )
            draft = next(
                (item for item in batch["items"] if item["eligibility"] == "eligible"),
                None,
            )
            if draft is None:
                raise RuntimeError(
                    "real webpage produced no eligible Evidence Draft: "
                    f"{[(item['eligibility'], item['block_reasons']) for item in batch['items']]}"
                )
            result = _expect(
                client.post(
                    f"/api/v1/projects/{project_id}/fragment-evidence-batches/"
                    f"{batch['fragment_evidence_batch_id']}/decision",
                    json={
                        "action": "confirm",
                        "selections": [
                            {
                                "fragment_evidence_item_id": draft[
                                    "fragment_evidence_item_id"
                                ],
                                "claim_type": draft["suggested_claim_type"],
                                "published_at": None,
                                "user_segment": None,
                            }
                        ],
                        "actor": "backend-smoke-test",
                        "reason": "Approve one exact excerpt after reviewing its locator.",
                    },
                ),
                200,
                "promote one real webpage fragment",
            )
            promoted = next(item for item in result["batch"]["items"] if item["selected"])
            evidence = promoted["evidence"]
            if evidence is None or not evidence["evidence_id"]:
                raise RuntimeError("real fragment was not assigned an Evidence ID")
            return {
                "project_id": project_id,
                "source_url": source["source_url"],
                "processing_status": processing["job"]["status"],
                "routing_status": routing["status"],
                "fragment_evidence_batch_id": batch["fragment_evidence_batch_id"],
                "batch_status": result["batch"]["status"],
                "eligible_count": batch["eligible_count"],
                "evidence_id": evidence["evidence_id"],
                "evidence_status": evidence["status"],
                "source_fragment_id": evidence["source_fragment_id"],
                "claim_type": evidence["claim_type"],
                "product": evidence["product"],
                "model_calls": 0,
            }


if __name__ == "__main__":
    print(json.dumps(run_live_smoke(), ensure_ascii=False, indent=2))
