import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.database.models import (
    EvidenceModel,
    FragmentEvidenceBatchItemModel,
    FragmentEvidenceBatchModel,
    ModelCallModel,
)
from app.main import create_app
from app.sources.search_discovery import SearchDiscoveryRegistry
from tests.integration.test_competitor_material_discovery_api import (
    MaterialSearchConnector,
    MaterialWebConnector,
    _project,
    _request,
    _settings,
)


def _material_source(client: TestClient, project_id: str) -> str:
    discovery = client.post(
        f"/api/v1/projects/{project_id}/competitor-material-discoveries",
        json={**_request(), "dimensions": ["official_product"]},
    )
    assert discovery.status_code == 201
    body = discovery.json()
    candidate_id = body["items"][0]["search_run"]["candidates"][0]["candidate_id"]
    decided = client.post(
        f"/api/v1/projects/{project_id}/competitor-material-discoveries/"
        f"{body['material_discovery_id']}/decision",
        json={
            "action": "confirm",
            "selected_candidate_ids": [candidate_id],
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "actor": "research-lead",
            "reason": "Allow this public page for the research project.",
        },
    )
    assert decided.status_code == 201
    return str(decided.json()["decision"]["selections"][0]["source_asset"]["source_asset_id"])


def test_verified_competitor_fragment_is_drafted_constrained_and_promoted(
    tmp_path: Path,
) -> None:
    search = MaterialSearchConnector()
    web = MaterialWebConnector()
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry((search,))
    application.state.web_connector = web

    with TestClient(application) as client:
        project_id = _project(client)
        source_asset_id = _material_source(client, project_id)
        processing = client.get(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
        )
        routing = client.get(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/routing"
        )
        fragments = client.get(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
        ).json()
        created = client.post(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches",
            json={
                "source_asset_ids": [source_asset_id],
                "source_fragment_ids": [
                    fragments["items"][0]["source_fragment_id"]
                ],
                "requested_by": "research-lead",
                "purpose": "Prepare verified official product excerpts for Evidence review.",
            },
        )
        batch = created.json()
        eligible = [item for item in batch["items"] if item["eligibility"] == "eligible"]
        selected = eligible[0]
        decision_payload = {
            "action": "confirm",
            "selections": [
                {
                    "fragment_evidence_item_id": selected["fragment_evidence_item_id"],
                    "claim_type": "vendor_claim",
                    "published_at": "2026-01-01T00:00:00Z",
                    "user_segment": None,
                }
            ],
            "actor": "research-lead",
            "reason": "The excerpt and locator were reviewed for Evidence use.",
        }
        decided = client.post(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches/"
            f"{batch['fragment_evidence_batch_id']}/decision",
            json=decision_payload,
        )
        repeated = client.post(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches/"
            f"{batch['fragment_evidence_batch_id']}/decision",
            json=decision_payload,
        )
        listed = client.get(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches"
        )
        evidence_page = client.get(f"/api/v1/projects/{project_id}/evidence")
        requirements = client.get(f"/api/v1/projects/{project_id}/source-requirements")
        metadata_conflict = client.post(
            f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments/"
            f"{selected['source_fragment']['source_fragment_id']}/evidence",
            json={
                "claim_type": "specification",
                "product": "Ring Battery Doorbell Pro",
                "region": None,
                "user_segment": None,
                "published_at": None,
                "confidence": 0.5,
                "authority_score": 0.5,
                "recency_score": 0.5,
                "diversity_score": 0.5,
            },
        )

    assert processing.status_code == 200
    assert processing.json()["job"]["status"] == "succeeded"
    assert routing.status_code == 200
    assert routing.json()["status"] == "confirmed"
    assert created.status_code == 201
    assert batch["status"] == "pending_review"
    assert batch["eligible_count"] >= 1
    assert selected["product"] == {
        "brand": "Ring",
        "model": "Battery Doorbell Pro",
        "variant": None,
    }
    assert selected["product_role"] == "competitor"
    assert selected["dimensions"] == ["official_product"]
    assert selected["suggested_claim_type"] == "vendor_claim"
    assert "vendor_claim" in selected["allowed_claim_types"]
    assert "user_opinion" not in selected["allowed_claim_types"]
    assert decided.status_code == 200
    assert decided.json()["decision_created"] is True
    final_batch = decided.json()["batch"]
    assert final_batch["status"] == "completed"
    assert final_batch["promoted_count"] == 1
    promoted = next(item for item in final_batch["items"] if item["selected"])
    evidence = promoted["evidence"]
    assert evidence["source_fragment_id"] == promoted["source_fragment"]["source_fragment_id"]
    assert evidence["product"] == "Ring Battery Doorbell Pro"
    assert evidence["claim_type"] == "vendor_claim"
    assert evidence["status"] == "partially_verified"
    assert evidence["confidence"] == 0.95
    assert evidence["authority_score"] == 0.85
    assert evidence["recency_score"] == 0.9
    assert repeated.status_code == 200
    assert repeated.json()["decision_created"] is False
    assert repeated.json()["batch"]["promoted_count"] == 1
    assert listed.json()["total"] == 1
    assert evidence_page.json()["total"] == 1
    official_requirement = next(
        item
        for item in requirements.json()["requirements"]
        if item["product_role"] == "competitor"
        and item["dimension"] == "official_product"
    )
    assert official_requirement["status"] == "satisfied"
    assert official_requirement["matched_evidence_ids"] == [evidence["evidence_id"]]
    assert metadata_conflict.status_code == 409
    assert metadata_conflict.json()["code"] == "EVIDENCE_CONTENT_METADATA_CONFLICT"
    assert len(search.calls or []) == 1
    assert len(web.calls) == 1

    async def audit() -> tuple[int, int, int, int]:
        async with application.state.database.session() as session:
            batches = int(
                await session.scalar(select(func.count()).select_from(FragmentEvidenceBatchModel))
                or 0
            )
            items = int(
                await session.scalar(
                    select(func.count()).select_from(FragmentEvidenceBatchItemModel)
                )
                or 0
            )
            evidence_count = int(
                await session.scalar(select(func.count()).select_from(EvidenceModel)) or 0
            )
            model_calls = int(
                await session.scalar(select(func.count()).select_from(ModelCallModel)) or 0
            )
        return batches, items, evidence_count, model_calls

    assert asyncio.run(audit()) == (1, 1, 1, 0)


def test_fragment_evidence_gate_rejects_disallowed_claim_type_and_conflicting_decision(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path))
    application.state.search_discovery_registry = SearchDiscoveryRegistry(
        (MaterialSearchConnector(),)
    )
    application.state.web_connector = MaterialWebConnector()
    with TestClient(application) as client:
        project_id = _project(client)
        source_asset_id = _material_source(client, project_id)
        created = client.post(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches",
            json={
                "source_asset_ids": [source_asset_id],
                "requested_by": "research-lead",
                "purpose": "Prepare Evidence Drafts.",
            },
        ).json()
        item_id = next(
            item["fragment_evidence_item_id"]
            for item in created["items"]
            if item["eligibility"] == "eligible"
        )
        disallowed = client.post(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches/"
            f"{created['fragment_evidence_batch_id']}/decision",
            json={
                "action": "confirm",
                "selections": [
                    {
                        "fragment_evidence_item_id": item_id,
                        "claim_type": "user_opinion",
                        "published_at": None,
                        "user_segment": None,
                    }
                ],
                "actor": "research-lead",
                "reason": "Attempt a disallowed classification.",
            },
        )
        rejected = client.post(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches/"
            f"{created['fragment_evidence_batch_id']}/decision",
            json={
                "action": "reject",
                "selections": [],
                "actor": "research-lead",
                "reason": "Do not use these excerpts.",
            },
        )
        conflict = client.post(
            f"/api/v1/projects/{project_id}/fragment-evidence-batches/"
            f"{created['fragment_evidence_batch_id']}/decision",
            json={
                "action": "confirm",
                "selections": [
                    {
                        "fragment_evidence_item_id": item_id,
                        "claim_type": "vendor_claim",
                        "published_at": None,
                        "user_segment": None,
                    }
                ],
                "actor": "research-lead",
                "reason": "Try to replace the saved rejection.",
            },
        )

    assert disallowed.status_code == 422
    assert disallowed.json()["code"] == "FRAGMENT_EVIDENCE_CLAIM_TYPE_NOT_ALLOWED"
    assert rejected.status_code == 200
    assert rejected.json()["batch"]["status"] == "rejected"
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "FRAGMENT_EVIDENCE_DECISION_CONFLICT"
