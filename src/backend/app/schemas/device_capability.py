"""设备能力图、家庭设备快照和确定性能力查询契约。"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=80)]
EvidenceId = Annotated[str, Field(min_length=1, max_length=80)]
CapabilityKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceCapabilityKind(StrEnum):
    SENSOR = "sensor"
    ACTION = "action"
    COMPUTE = "compute"
    STORAGE = "storage"
    CONNECTIVITY = "connectivity"
    CONTEXT = "context"


class CapabilityAssertion(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class CapabilityAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DeviceDataScope(StrEnum):
    DEVICE_LOCAL = "device_local"
    HOMEBASE_LOCAL = "homebase_local"
    CLOUD = "cloud"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class OfflineSupport(StrEnum):
    FULL = "full"
    DEGRADED = "degraded"
    NONE = "none"
    UNKNOWN = "unknown"


class DeviceLifecycleStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    UNKNOWN = "unknown"


class HouseholdLocationType(StrEnum):
    ENTRANCE = "entrance"
    EXTERIOR = "exterior"
    INTERIOR = "interior"
    GARAGE = "garage"
    YARD = "yard"
    SHARED_AREA = "shared_area"
    OTHER = "other"


class HouseholdRuntimeStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class HouseholdAuthorizationStatus(StrEnum):
    AUTHORIZED = "authorized"
    DENIED = "denied"
    UNKNOWN = "unknown"


class DeviceRelationType(StrEnum):
    CONNECTED_TO = "connected_to"
    SENDS_EVENTS_TO = "sends_events_to"
    CONTROLS = "controls"
    SHARES_CONTEXT_WITH = "shares_context_with"


class RelationVerificationStatus(StrEnum):
    CONFIRMED = "confirmed"
    USER_DECLARED = "user_declared"
    UNKNOWN = "unknown"


class CapabilityQueryStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class DeviceCapabilityClaimInput(StrictModel):
    capability_key: CapabilityKey
    capability_name: str = Field(min_length=1, max_length=160)
    kind: DeviceCapabilityKind
    assertion: CapabilityAssertion
    availability: CapabilityAvailability
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=30)
    latency_ms_max: int | None = Field(default=None, ge=0, le=3_600_000)
    data_scope: DeviceDataScope
    authorization_required: bool
    offline_support: OfflineSupport
    fallback: str | None = Field(default=None, max_length=500)

    @field_validator("capability_name", "fallback", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("capability evidence_ids must be unique")
        return value


class DeviceCapabilityClaim(DeviceCapabilityClaimInput):
    capability_claim_id: Identifier


class CatalogDeviceCreate(StrictModel):
    manufacturer: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    lifecycle_status: DeviceLifecycleStatus
    identity_evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=30)
    capabilities: list[DeviceCapabilityClaimInput] = Field(min_length=1, max_length=100)

    @field_validator("manufacturer", "product_name", "model", "category", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("identity_evidence_ids")
    @classmethod
    def identity_evidence_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("identity_evidence_ids must be unique")
        return value

    @field_validator("capabilities")
    @classmethod
    def exact_capability_claims_must_be_unique(
        cls, value: list[DeviceCapabilityClaimInput]
    ) -> list[DeviceCapabilityClaimInput]:
        identities = [
            (
                item.capability_key,
                item.kind,
                item.assertion,
                tuple(sorted(item.evidence_ids)),
            )
            for item in value
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate capability claim")
        return value


class CatalogDevice(StrictModel):
    catalog_device_id: Identifier
    project_id: Identifier
    manufacturer: str
    product_name: str
    model: str
    category: str
    lifecycle_status: DeviceLifecycleStatus
    identity_evidence_ids: list[EvidenceId]
    capabilities: list[DeviceCapabilityClaim]
    created_at: datetime
    updated_at: datetime


class CatalogDevicePage(StrictModel):
    items: list[CatalogDevice]
    total: int = Field(ge=0)


class HouseholdLocationInput(StrictModel):
    location_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    label: str = Field(min_length=1, max_length=120)
    location_type: HouseholdLocationType

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class HouseholdDeviceInput(StrictModel):
    household_device_id: str = Field(pattern=r"^home_device_[A-Za-z0-9_-]+$")
    catalog_device_id: str | None = Field(
        default=None, pattern=r"^device_[A-Za-z0-9_-]+$"
    )
    display_name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    location_id: Identifier
    runtime_status: HouseholdRuntimeStatus
    authorization_status: HouseholdAuthorizationStatus

    @field_validator("display_name", "category", "model", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class HouseholdDeviceRelationInput(StrictModel):
    relation_id: str = Field(pattern=r"^relation_[A-Za-z0-9_-]+$")
    source_household_device_id: Identifier
    target_household_device_id: Identifier
    relation_type: DeviceRelationType
    verification_status: RelationVerificationStatus
    evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=30)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("relation evidence_ids must be unique")
        return value

    @model_validator(mode="after")
    def confirmed_relation_requires_evidence(self) -> "HouseholdDeviceRelationInput":
        if self.source_household_device_id == self.target_household_device_id:
            raise ValueError("device relation cannot reference itself")
        if self.verification_status is RelationVerificationStatus.CONFIRMED:
            if not self.evidence_ids:
                raise ValueError("confirmed relation requires evidence_ids")
        return self


class HouseholdSnapshotCreate(StrictModel):
    authorization_confirmed: Literal[True]
    authorized_by: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=300)
    locations: list[HouseholdLocationInput] = Field(min_length=1, max_length=50)
    devices: list[HouseholdDeviceInput] = Field(min_length=1, max_length=100)
    relations: list[HouseholdDeviceRelationInput] = Field(default_factory=list, max_length=200)

    @field_validator("authorized_by", "purpose", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def references_must_be_internal_and_unique(self) -> "HouseholdSnapshotCreate":
        location_ids = [item.location_id for item in self.locations]
        device_ids = [item.household_device_id for item in self.devices]
        relation_ids = [item.relation_id for item in self.relations]
        for label, values in (
            ("location_id", location_ids),
            ("household_device_id", device_ids),
            ("relation_id", relation_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label}")
        known_locations = set(location_ids)
        invalid_locations = sorted(
            {item.location_id for item in self.devices} - known_locations
        )
        if invalid_locations:
            raise ValueError(f"unknown location_ids: {invalid_locations}")
        known_devices = set(device_ids)
        relation_device_ids = {
            value
            for relation in self.relations
            for value in (
                relation.source_household_device_id,
                relation.target_household_device_id,
            )
        }
        invalid_devices = sorted(relation_device_ids - known_devices)
        if invalid_devices:
            raise ValueError(f"unknown household_device_ids: {invalid_devices}")
        return self


class HouseholdSnapshot(HouseholdSnapshotCreate):
    snapshot_id: Identifier
    project_id: Identifier
    version: int = Field(ge=1)
    status: Literal["active"] = "active"
    created_at: datetime


class DeviceCapabilityRequirement(StrictModel):
    capability_key: CapabilityKey
    location_id: Identifier | None = None
    kind: DeviceCapabilityKind | None = None


class DeviceCapabilityQuery(StrictModel):
    requirements: list[DeviceCapabilityRequirement] = Field(min_length=1, max_length=50)

    @field_validator("requirements")
    @classmethod
    def requirements_must_be_unique(
        cls, value: list[DeviceCapabilityRequirement]
    ) -> list[DeviceCapabilityRequirement]:
        identities = [
            (item.capability_key, item.location_id, item.kind) for item in value
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate capability requirement")
        return value


class DeviceCapabilityMatch(StrictModel):
    household_device_id: Identifier
    catalog_device_id: Identifier
    display_name: str
    location_id: Identifier
    capability_claim_ids: list[Identifier]
    evidence_ids: list[EvidenceId]


class DeviceCapabilityRequirementResult(StrictModel):
    requirement: DeviceCapabilityRequirement
    status: CapabilityQueryStatus
    matches: list[DeviceCapabilityMatch]
    issues: list[str]


class DeviceCapabilityQueryResult(StrictModel):
    project_id: Identifier
    snapshot_id: Identifier
    snapshot_version: int = Field(ge=1)
    overall_status: CapabilityQueryStatus
    requirements: list[DeviceCapabilityRequirementResult] = Field(min_length=1)
    cited_evidence_ids: list[EvidenceId]
