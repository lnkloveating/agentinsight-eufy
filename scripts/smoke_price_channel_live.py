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

from app.agents.competitor import PriceChannelEvidenceContextBuilder
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
from smoke_user_research_live import DEFAULT_URLS, _expect

PRICE_PATTERN = re.compile(
    r"(?:\$|€|£|¥)\s?\d|\b(?:USD|AUD|EUR|GBP|CNY)\b", re.IGNORECASE
)
CHANNEL_TERMS = (
    "in stock",
    "out of stock",
    "add to cart",
    "buy now",
    "preorder",
    "sold by",
    "库存",
    "加入购物车",
)


def _create_and_approve_project(client: TestClient, model_id: str, product: str) -> str:
    project = _expect(
        client.post(
            "/api/v1/projects",
            json={
                "brief": {
                    "question": f"What US price and channel facts are supported for {product}?",
                    "category": "eufy home security",
                    "target_user": "US households",
                    "region": "US",
                    "scenarios": ["authorized online purchase"],
                    "constraints": ["evidence only", "time-bounded observations"],
                    "focus_dimensions": ["price", "availability", "seller", "promotion"],
                },
                "model_selection": {
                    "default_model_id": model_id,
                    "agent_overrides": {"competitor_research": model_id},
                },
            },
        ),
        201,
        "create price-channel project",
    )
    project_id = str(project["project_id"])
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/decisions",
            json={
                "decision_id": project["pending_decision"]["decision_id"],
                "action": "approve",
                "reason": "The exact product, US region and public source are authorized.",
                "actor": "backend-smoke-test",
            },
        ),
        202,
        "approve price-channel project",
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
            "list price page fragments",
        )
        fragments.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return fragments


def _select_fragments(
    fragments: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(fragments) < 2:
        raise RuntimeError("price-channel smoke needs at least two distinct source fragments")
    price = next(
        (
            item
            for item in fragments
            if PRICE_PATTERN.search(str(item.get("original_excerpt", "")))
        ),
        None,
    )
    if price is None:
        raise RuntimeError("authorized page contained no explicit currency-price fragment")
    channel = next(
        (
            item
            for item in fragments
            if item["source_fragment_id"] != price["source_fragment_id"]
            and any(
                term in str(item.get("original_excerpt", "")).casefold()
                for term in CHANNEL_TERMS
            )
        ),
        None,
    )
    if channel is None:
        channel = next(
            item
            for item in fragments
            if item["source_fragment_id"] != price["source_fragment_id"]
        )
    return price, channel


def _promote(
    client: TestClient,
    project_id: str,
    source_asset_id: str,
    fragment: dict[str, Any],
    *,
    claim_type: str,
    product: str,
) -> str:
    result = _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments/"
            f"{fragment['source_fragment_id']}/evidence",
            json={
                "claim_type": claim_type,
                "product": product,
                "region": "US",
                "confidence": 0.75,
                "authority_score": 0.9,
                "recency_score": 0.8,
                "diversity_score": 0.3,
            },
        ),
        201,
        f"promote {claim_type} evidence",
    )
    return str(result["evidence"]["evidence_id"])


def _process_price_page(
    client: TestClient, project_id: str, source_url: str, product: str
) -> dict[str, Any]:
    registered = _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/links",
            json={
                "source_url": source_url,
                "display_name": f"Authorized price page for {product}",
                "authorization_basis": "publicly_available",
                "authorization_confirmed": True,
                "authorized_by": "backend-smoke-test",
                "purpose": "US price retail channel availability research",
            },
        ),
        201,
        "register price webpage",
    )
    source_asset_id = str(registered["source_asset"]["source_asset_id"])
    processing = _expect(
        client.post(f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"),
        200,
        "process price webpage",
    )
    if processing["job"]["status"] != "succeeded":
        raise RuntimeError(
            "price webpage processing failed: "
            f"{processing['job'].get('error_code')} {processing['job'].get('error_message')}"
        )
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/analyze",
            json={"use_model": False},
        ),
        200,
        "analyze price routing",
    )
    _expect(
        client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing/decision",
            json={
                "action": "confirm",
                "selections": [
                    {
                        "route": "price_channel",
                        "claim_types": ["price_observation", "channel_availability"],
                    }
                ],
                "actor": "backend-smoke-test",
                "reason": "Reviewed public product page contains price and listing context.",
            },
        ),
        200,
        "confirm price routing",
    )
    fragments = _list_fragments(client, project_id, source_asset_id)
    price_fragment, channel_fragment = _select_fragments(fragments)
    evidence_ids = [
        _promote(
            client,
            project_id,
            source_asset_id,
            price_fragment,
            claim_type="price_observation",
            product=product,
        ),
        _promote(
            client,
            project_id,
            source_asset_id,
            channel_fragment,
            claim_type="channel_availability",
            product=product,
        ),
    ]
    return {
        "source_asset_id": source_asset_id,
        "fragment_count": len(fragments),
        "evidence_ids": evidence_ids,
        "parser_id": processing["parsed_artifact"]["parser_id"],
    }


async def _run_specialist(application: Any, project_id: str, product: str) -> dict[str, Any]:
    evidence_context = await PriceChannelEvidenceContextBuilder(
        application.state.database,
        max_items=60,
        max_excerpt_chars=3_000,
        max_total_chars=80_000,
    ).build(project_id, region="US")
    task = ResearchTask(
        task_id="task_live_price_channel",
        project_id=project_id,
        agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
        goal="Extract evidence-backed, time-bounded price channel intelligence.",
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
            "trace_live_price_channel",
        ).execute(
            task,
            AgentContext(
                project_id=project_id,
                brief=ResearchBrief(
                    question=f"What US price and channel facts are supported for {product}?",
                    category="eufy home security",
                    target_user="US households",
                    region="US",
                    scenarios=["authorized online purchase"],
                ),
                iteration=0,
                evidence_context=evidence_context,
            ),
        )
    except RuntimeGatewayError as exc:
        raise RuntimeError(f"price-channel specialist failed: {exc.code}") from exc
    async with application.state.database.session() as session:
        tasks = await A2ATaskRepository(session).list_for_parent(project_id, task.task_id)
        runs = await ProjectRepository(session).list_agent_runs(project_id)
        run = next(item for item in runs if item.task_id == task.task_id)
        model_calls = await ModelCallRepository(session).list_for_run(run.agent_run_id)
    price_task = next(item for item in tasks if item.specialist_type == "price_channel")
    output = price_task.output_json or {}
    payload = output.get("structured_payload", {})
    return {
        "parent_artifact_status": artifact.status,
        "price_task_status": price_task.status,
        "evidence_context_count": evidence_context.included_evidence_count,
        "cited_evidence_count": len(output.get("evidence_ids", [])),
        "price_observation_count": len(payload.get("price_observations", [])),
        "channel_observation_count": len(payload.get("channel_observations", [])),
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
    with TemporaryDirectory(prefix="agentinsight-price-channel-") as temp_root:
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
                page = _process_price_page(client, project_id, source_url, product)
                result = asyncio.run(_run_specialist(application, project_id, product))
                result.update(
                    {
                        "model_id": model_id,
                        "fragment_count": page["fragment_count"],
                        "promoted_evidence_count": len(page["evidence_ids"]),
                        "parser_id": page["parser_id"],
                    }
                )
                results.append(result)
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Run a real authorized webpage through the price-channel A2A specialist."
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--url", default=DEFAULT_URLS[0])
    parser.add_argument("--product", default="eufy authorized product")
    args = parser.parse_args()
    results = run_live_smoke(
        args.models or ["anker:glm-5.2", "anker:deepseek-v4-pro"],
        args.url,
        args.product,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
