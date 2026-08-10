from datetime import UTC, datetime

from app.application.device_capabilities import DeviceCapabilityService
from app.infrastructure.database.models import (
    DeviceCapabilityClaimModel,
    DeviceCatalogModel,
    HouseholdDeviceModel,
)
from app.schemas.device_capability import (
    CapabilityQueryStatus,
    DeviceCapabilityRequirement,
)


def _claim(
    claim_id: str,
    *,
    assertion: str = "supported",
    availability: str = "available",
    offline_support: str = "none",
    evidence_id: str = "evidence_capability",
) -> DeviceCapabilityClaimModel:
    return DeviceCapabilityClaimModel(
        capability_claim_id=claim_id,
        project_id="proj_test",
        catalog_device_id="device_test",
        capability_key="vision.package_presence",
        capability_name="Package presence observation",
        kind="sensor",
        assertion=assertion,
        availability=availability,
        confidence=0.9,
        evidence_ids_json=[evidence_id],
        latency_ms_max=2000,
        data_scope="device_local",
        authorization_required=True,
        offline_support=offline_support,
        fallback=None,
        created_at=datetime.now(UTC),
    )


def _device(
    claims: list[DeviceCapabilityClaimModel] | None,
    *,
    runtime_status: str = "online",
    authorization_status: str = "authorized",
) -> HouseholdDeviceModel:
    now = datetime.now(UTC)
    device = HouseholdDeviceModel(
        household_device_record_id="home_record_test",
        household_device_id="home_device_doorbell",
        snapshot_id="snapshot_test",
        project_id="proj_test",
        catalog_device_id="device_test" if claims is not None else None,
        display_name="Front doorbell",
        category="doorbell",
        model="E340",
        location_id="front_door",
        runtime_status=runtime_status,
        authorization_status=authorization_status,
        created_at=now,
    )
    if claims is not None:
        catalog = DeviceCatalogModel(
            catalog_device_id="device_test",
            project_id="proj_test",
            manufacturer="eufy",
            product_name="Video Doorbell E340",
            model="E340",
            category="doorbell",
            lifecycle_status="active",
            identity_evidence_ids_json=["evidence_identity"],
            created_at=now,
            updated_at=now,
        )
        catalog.capability_claims = claims
        device.catalog_device = catalog
    return device


def _evaluate(device: HouseholdDeviceModel):  # type: ignore[no-untyped-def]
    service = DeviceCapabilityService(None, None, None, "trace_test")  # type: ignore[arg-type]
    evidence_ids = (
        set(device.catalog_device.identity_evidence_ids_json)
        | {
            evidence_id
            for claim in device.catalog_device.capability_claims
            for evidence_id in claim.evidence_ids_json
        }
        if device.catalog_device is not None
        else set()
    )
    return service._evaluate_requirement(
        [device],
        DeviceCapabilityRequirement(
            capability_key="vision.package_presence",
            location_id="front_door",
            kind="sensor",
        ),
        eligible_evidence_ids=evidence_ids,
    )


def test_supported_online_authorized_device_is_available_and_cites_evidence() -> None:
    result = _evaluate(_device([_claim("cap_supported")]))
    assert result.status is CapabilityQueryStatus.AVAILABLE
    assert result.matches[0].capability_claim_ids == ["cap_supported"]
    assert result.matches[0].evidence_ids == ["evidence_capability"]


def test_support_and_limitation_evidence_are_reported_as_conflict() -> None:
    result = _evaluate(
        _device(
            [
                _claim("cap_supported"),
                _claim(
                    "cap_unsupported",
                    assertion="unsupported",
                    evidence_id="evidence_limitation",
                ),
            ]
        )
    )
    assert result.status is CapabilityQueryStatus.CONFLICT
    assert "CONFLICTING_CAPABILITY_EVIDENCE" in result.issues
    assert result.matches[0].evidence_ids == [
        "evidence_capability",
        "evidence_limitation",
    ]


def test_offline_without_offline_support_is_unavailable() -> None:
    result = _evaluate(
        _device([_claim("cap_supported", offline_support="none")], runtime_status="offline")
    )
    assert result.status is CapabilityQueryStatus.UNAVAILABLE
    assert "DEVICE_OFFLINE_NO_FALLBACK" in result.issues


def test_unmapped_household_device_is_unknown_instead_of_guessed() -> None:
    result = _evaluate(_device(None))
    assert result.status is CapabilityQueryStatus.UNKNOWN
    assert result.matches == []
    assert "UNMAPPED_HOUSEHOLD_DEVICE" in result.issues


def test_stale_capability_evidence_cannot_remain_available() -> None:
    device = _device([_claim("cap_supported")])
    service = DeviceCapabilityService(None, None, None, "trace_test")  # type: ignore[arg-type]
    result = service._evaluate_requirement(
        [device],
        DeviceCapabilityRequirement(
            capability_key="vision.package_presence",
            location_id="front_door",
            kind="sensor",
        ),
        eligible_evidence_ids={"evidence_identity"},
    )
    assert result.status is CapabilityQueryStatus.UNKNOWN
    assert result.matches == []
    assert "CAPABILITY_EVIDENCE_STALE" in result.issues
    assert "CAPABILITY_HAS_NO_CURRENT_EVIDENCE" in result.issues
