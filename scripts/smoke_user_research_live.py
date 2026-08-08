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

from app.application.model_gateway import (
    EnvironmentCredentialResolver,
    ModelCatalog,
    OpenAICompatibleProvider,
    ProviderModelRequest,
    parse_openai_compatible_provider_configs,
)
from app.application.model_gateway.contracts import ModelMessage
from app.core.config import Settings
from app.main import create_app

DEFAULT_URLS = (
    "https://www.eufy.com/products/t85m0j11?variant=46155922538682",
    "https://www.eufy.com/products/t80301d1?variant=41846278357178",
)
KEYWORDS = ("doorbell", "package", "delivery", "homebase", "dual cam", "local")
USER_OPINION_KEYWORDS = (
    "false",
    "problem",
    "issue",
    "alert",
    "notification",
    "delay",
    "lag",
    "frustrat",
    "miss",
    "detect",
)


def _expect(response: Any, expected: int, operation: str) -> Any:
    if response.status_code != expected:
        body = response.json()
        raise RuntimeError(
            f"{operation} failed ({response.status_code}): "
            f"{body.get('code', 'UNKNOWN')} {body.get('message', '')}"
        )
    return response.json()


def _create_and_approve_project(client: TestClient, model_id: str) -> str:
    project = _expect(
        client.post(
            "/api/v1/projects",
            json={
                "brief": {
                    "question": (
                        "What user needs can and cannot be established from the "
                        "provided eufy doorbell and HomeBase product pages?"
                    ),
                    "category": "home security",
                    "target_user": "North American smart doorbell users",
                    "region": "US",
                    "scenarios": ["package delivery", "doorstep monitoring"],
                    "constraints": ["privacy first", "evidence only"],
                    "focus_dimensions": ["user events", "pain points", "research gaps"],
                },
                "model_selection": {
                    "default_model_id": model_id,
                    "agent_overrides": {"user_research": model_id},
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
                "reason": "Live smoke-test scope is explicit.",
                "actor": "backend-smoke-test",
            },
        ),
        202,
        "approve project",
    )
    return project_id


def _select_fragments(
    items: list[dict[str, Any]], *, claim_type: str
) -> list[dict[str, Any]]:
    keywords = USER_OPINION_KEYWORDS if claim_type == "user_opinion" else KEYWORDS
    meaningful = []
    for item in items:
        excerpt = str(item.get("original_excerpt", ""))
        lowered = excerpt.lower()
        keyword_count = sum(keyword in lowered for keyword in keywords)
        if keyword_count:
            meaningful.append((keyword_count, min(len(excerpt), 1_000), item))
    meaningful.sort(key=lambda candidate: (candidate[0], candidate[1]), reverse=True)
    ranked = [item for _, _, item in meaningful]
    return (ranked or items)[:1]


async def probe_models(model_ids: list[str]) -> list[dict[str, Any]]:
    """Verify model routing, credential and structured JSON with a tiny request."""
    if not ENVIRONMENT_PATH.is_file():
        raise RuntimeError("src/backend/.env is required for the live smoke test")
    settings = Settings(_env_file=ENVIRONMENT_PATH)
    catalog = ModelCatalog.from_json(
        settings.model_catalog_json,
        default_model_id=settings.default_model_id,
    )
    credentials = EnvironmentCredentialResolver.from_dotenv(str(ENVIRONMENT_PATH))
    providers = {
        config.provider_id: OpenAICompatibleProvider(
            config.provider_id, config.base_url
        )
        for config in parse_openai_compatible_provider_configs(
            settings.openai_compatible_providers_json
        )
    }
    results: list[dict[str, Any]] = []
    for model_id in model_ids:
        model = catalog.require_enabled(model_id)
        credential = credentials.resolve(model.credential_env)
        if credential is None:
            raise RuntimeError(f"credential is missing for {model_id}")
        provider = providers[model.provider]
        result = await provider.generate(
            ProviderModelRequest(
                provider_model=model.provider_model,
                credential=credential,
                messages=(
                    ModelMessage(
                        role="user",
                        content='Return exactly one JSON object: {"status":"ok"}.',
                    ),
                ),
                response_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "const": "ok"}
                    },
                    "required": ["status"],
                    "additionalProperties": False,
                },
                timeout_seconds=90,
                max_output_tokens=1_024,
                options={
                    **model.provider_options,
                    "thinking": {"type": "disabled"},
                },
            )
        )
        raw_output = result.output
        payload = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise RuntimeError(f"{model_id} returned an invalid probe payload")
        results.append(
            {
                "model_id": model_id,
                "status": "ok",
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "provider_request_received": bool(result.provider_request_id),
            }
        )
    return results


def _process_page(
    client: TestClient,
    project_id: str,
    source_url: str,
    *,
    claim_type: str,
) -> tuple[dict[str, Any], list[str]]:
    registered = _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/links",
            json={
                "source_url": source_url,
                "display_name": "eufy official product page",
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "authorized_by": "backend-smoke-test",
                "purpose": "Validate the live user-research evidence path",
            },
        ),
        201,
        "register webpage",
    )
    source_asset_id = str(registered["source_asset"]["source_asset_id"])
    processed = _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
        ),
        200,
        "process webpage",
    )
    if processed["job"]["status"] != "succeeded":
        raise RuntimeError(
            "process webpage did not succeed: "
            f"{processed['job'].get('error_code')} "
            f"{processed['job'].get('error_message')}"
        )
    fragments: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        response = client.get(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments",
            params={"cursor": cursor} if cursor is not None else None,
        )
        fragment_page = _expect(response, 200, "list webpage fragments")
        fragments.extend(fragment_page["items"])
        cursor = fragment_page["next_cursor"]
        if cursor is None:
            break
    if not fragments:
        raise RuntimeError("live webpage produced no verified source fragments")
    evidence_ids: list[str] = []
    for fragment in _select_fragments(fragments, claim_type=claim_type):
        promoted = client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}"
            f"/fragments/{fragment['source_fragment_id']}/evidence",
            json={
                "claim_type": claim_type,
                "product": "eufy home security",
                "region": "US",
                "confidence": 0.75,
                "authority_score": 0.9,
                "recency_score": 0.7,
                "diversity_score": 0.3,
            },
        )
        if promoted.status_code not in {200, 201}:
            _expect(promoted, 201, "promote webpage fragment")
        evidence_ids.append(str(promoted.json()["evidence"]["evidence_id"]))
    return (
        {
            "requested_url": source_url,
            "final_url": processed["job"]["result"]["final_url"],
            "parser_id": processed["parsed_artifact"]["parser_id"],
            "fragment_count": len(fragments),
            "selected_excerpts": [
                str(item["original_excerpt"])[:180]
                for item in _select_fragments(fragments, claim_type=claim_type)
            ],
        },
        list(dict.fromkeys(evidence_ids)),
    )


def run_live_smoke(
    model_ids: list[str], urls: list[str], *, claim_type: str
) -> list[dict[str, Any]]:
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
    with TemporaryDirectory(prefix="agentinsight-user-research-") as temp_root:
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
        with TestClient(create_app(settings)) as client:
            for model_id in model_ids:
                project_id = _create_and_approve_project(client, model_id)
                pages: list[dict[str, Any]] = []
                evidence_ids: list[str] = []
                for source_url in urls:
                    page, promoted_ids = _process_page(
                        client,
                        project_id,
                        source_url,
                        claim_type=claim_type,
                    )
                    pages.append(page)
                    evidence_ids.extend(promoted_ids)
                research = _expect(
                    client.post(
                        f"/api/v1/projects/{project_id}/agents/user-research"
                    ),
                    200,
                    f"run user research with {model_id}",
                )
                agents = _expect(
                    client.get(f"/api/v1/projects/{project_id}/agents"),
                    200,
                    "list agent runs",
                )
                user_run = next(
                    run for run in agents if run["agent_type"] == "user_research"
                )
                results.append(
                    {
                        "model_id": model_id,
                        "pages": pages,
                        "promoted_evidence_count": len(set(evidence_ids)),
                        "artifact_status": research["status"],
                        "artifact_evidence_count": len(research["evidence_ids"]),
                        "pain_point_count": len(
                            research["payload"]["pain_points"]
                        ),
                        "unmet_need_count": len(
                            research["payload"]["unmet_needs"]
                        ),
                        "research_gap_count": len(
                            research["payload"]["research_gaps"]
                        ),
                        "quality_score": research["quality_score"],
                        "input_tokens": user_run["input_tokens"],
                        "output_tokens": user_run["output_tokens"],
                    }
                )
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Run live webpage-to-user-research smoke tests without persisting data."
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Configured model ID; may be supplied multiple times.",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Authorized public webpage; may be supplied multiple times.",
    )
    parser.add_argument(
        "--claim-type",
        choices=("vendor_claim", "user_opinion", "fact"),
        default="vendor_claim",
        help="Evidence classification applied after inspecting the supplied pages.",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Only verify both configured models with a tiny structured request.",
    )
    args = parser.parse_args()
    models = args.models or ["anker:glm-5.2", "anker:deepseek-v4-pro"]
    urls = args.urls or list(DEFAULT_URLS)
    result = (
        asyncio.run(probe_models(models))
        if args.probe_only
        else run_live_smoke(models, urls, claim_type=args.claim_type)
    )
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
