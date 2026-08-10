from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.schemas.device_capability import (
    CatalogDeviceCreate,
    DeviceCapabilityQuery,
    HouseholdDeviceRelationInput,
    HouseholdSnapshotCreate,
)


def _capability() -> dict[str, object]:
    return {
        "capability_key": "vision.package_presence",
        "capability_name": "Package presence observation",
        "kind": "sensor",
        "assertion": "supported",
        "availability": "available",
        "confidence": 0.92,
        "evidence_ids": ["evidence_capability"],
        "latency_ms_max": 2000,
        "data_scope": "device_local",
        "authorization_required": True,
        "offline_support": "degraded",
        "fallback": "Retain a local event for later delivery.",
    }


def _snapshot() -> dict[str, object]:
    return {
        "authorization_confirmed": True,
        "authorized_by": "research-lead",
        "purpose": "Evaluate device coverage without retaining household media.",
        "locations": [
            {"location_id": "front_door", "label": "Front door", "location_type": "entrance"}
        ],
        "devices": [
            {
                "household_device_id": "home_device_doorbell",
                "catalog_device_id": "device_e340",
                "display_name": "Front doorbell",
                "category": "doorbell",
                "model": "E340",
                "location_id": "front_door",
                "runtime_status": "online",
                "authorization_status": "authorized",
            },
            {
                "household_device_id": "home_device_homebase",
                "catalog_device_id": "device_s380",
                "display_name": "HomeBase",
                "category": "homebase",
                "model": "S380",
                "location_id": "front_door",
                "runtime_status": "online",
                "authorization_status": "authorized",
            },
        ],
        "relations": [
            {
                "relation_id": "relation_doorbell_homebase",
                "source_household_device_id": "home_device_doorbell",
                "target_household_device_id": "home_device_homebase",
                "relation_type": "sends_events_to",
                "verification_status": "confirmed",
                "evidence_ids": ["evidence_compatibility"],
            }
        ],
    }


def test_catalog_contract_allows_conflicting_claims_but_not_exact_duplicates() -> None:
    supported = _capability()
    unsupported = {**supported, "assertion": "unsupported", "evidence_ids": ["evidence_limit"]}
    device = CatalogDeviceCreate.model_validate(
        {
            "manufacturer": "eufy",
            "product_name": "Video Doorbell E340",
            "model": "E340",
            "category": "doorbell",
            "lifecycle_status": "active",
            "identity_evidence_ids": ["evidence_identity"],
            "capabilities": [supported, unsupported],
        }
    )
    assert len(device.capabilities) == 2

    with pytest.raises(ValidationError, match="duplicate capability claim"):
        CatalogDeviceCreate.model_validate(
            {
                "manufacturer": "eufy",
                "product_name": "Video Doorbell E340",
                "model": "E340",
                "category": "doorbell",
                "lifecycle_status": "active",
                "identity_evidence_ids": ["evidence_identity"],
                "capabilities": [supported, supported],
            }
        )


def test_household_snapshot_enforces_internal_references_and_excludes_sensitive_fields() -> None:
    parsed = HouseholdSnapshotCreate.model_validate(_snapshot())
    assert parsed.devices[0].location_id == "front_door"

    invalid_location = _snapshot()
    invalid_location["devices"][0]["location_id"] = "unknown_room"  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown location_ids"):
        HouseholdSnapshotCreate.model_validate(invalid_location)

    sensitive = _snapshot()
    sensitive["devices"][0]["serial_number"] = "must-not-be-collected"  # type: ignore[index]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HouseholdSnapshotCreate.model_validate(sensitive)


def test_confirmed_relation_requires_evidence_and_cannot_reference_itself() -> None:
    with pytest.raises(ValidationError, match="confirmed relation requires evidence_ids"):
        HouseholdDeviceRelationInput.model_validate(
            {
                "relation_id": "relation_one",
                "source_household_device_id": "home_device_one",
                "target_household_device_id": "home_device_two",
                "relation_type": "connected_to",
                "verification_status": "confirmed",
                "evidence_ids": [],
            }
        )
    with pytest.raises(ValidationError, match="cannot reference itself"):
        HouseholdDeviceRelationInput.model_validate(
            {
                "relation_id": "relation_one",
                "source_household_device_id": "home_device_one",
                "target_household_device_id": "home_device_one",
                "relation_type": "connected_to",
                "verification_status": "user_declared",
                "evidence_ids": [],
            }
        )


def test_capability_query_rejects_duplicate_requirements() -> None:
    with pytest.raises(ValidationError, match="duplicate capability requirement"):
        DeviceCapabilityQuery.model_validate(
            {
                "requirements": [
                    {"capability_key": "vision.package_presence", "location_id": "front_door"},
                    {"capability_key": "vision.package_presence", "location_id": "front_door"},
                ]
            }
        )


def test_openapi_exposes_the_same_device_capability_contract() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    document = yaml.safe_load(
        (repository_root / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )
    paths = document["paths"]
    schemas = document["components"]["schemas"]
    assert "/projects/{project_id}/device-capabilities/catalog" in paths
    assert "/projects/{project_id}/device-capabilities/household-snapshot" in paths
    assert "/projects/{project_id}/device-capabilities/queries" in paths
    assert schemas["DeviceCapabilityQueryResult"]["properties"]["overall_status"][
        "enum"
    ] == ["available", "unavailable", "unknown", "conflict"]
    assert schemas["HouseholdDeviceInput"]["additionalProperties"] is False
    assert "serial_number" not in schemas["HouseholdDeviceInput"]["properties"]
