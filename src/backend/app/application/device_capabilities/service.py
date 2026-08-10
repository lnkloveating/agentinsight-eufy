"""证据约束的设备能力目录、家庭快照和能力覆盖查询。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.device_capability_repository import (
    DeviceCapabilityRepository,
)
from app.infrastructure.database.models import (
    DeviceCapabilityClaimModel,
    DeviceCatalogModel,
    HouseholdDeviceModel,
    HouseholdDeviceRelationModel,
    HouseholdSnapshotModel,
    ProjectEventModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.device_capability import (
    CapabilityAssertion,
    CapabilityAvailability,
    CapabilityQueryStatus,
    CatalogDevice,
    CatalogDeviceCreate,
    CatalogDevicePage,
    DeviceCapabilityClaim,
    DeviceCapabilityClaimInput,
    DeviceCapabilityKind,
    DeviceCapabilityMatch,
    DeviceCapabilityQuery,
    DeviceCapabilityQueryResult,
    DeviceCapabilityRequirement,
    DeviceCapabilityRequirementResult,
    DeviceDataScope,
    DeviceLifecycleStatus,
    DeviceRelationType,
    HouseholdAuthorizationStatus,
    HouseholdDeviceInput,
    HouseholdDeviceRelationInput,
    HouseholdLocationInput,
    HouseholdRuntimeStatus,
    HouseholdSnapshot,
    HouseholdSnapshotCreate,
    OfflineSupport,
    RelationVerificationStatus,
)
from app.schemas.evidence import EvidenceStatus

_ELIGIBLE_EVIDENCE_STATUSES = {
    EvidenceStatus.VERIFIED.value,
    EvidenceStatus.PARTIALLY_VERIFIED.value,
}


class DeviceCapabilityService:
    def __init__(
        self,
        repository: DeviceCapabilityRepository,
        project_repository: ProjectRepository,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.event_broker = event_broker
        self.trace_id = trace_id

    async def create_catalog_device(
        self, project_id: str, payload: CatalogDeviceCreate
    ) -> CatalogDevice:
        await self._require_project(project_id)
        await self._validate_evidence(project_id, self._catalog_evidence_ids(payload))
        now = datetime.now(UTC)
        model = DeviceCatalogModel(
            catalog_device_id=f"device_{uuid4().hex[:16]}",
            project_id=project_id,
            manufacturer=payload.manufacturer,
            product_name=payload.product_name,
            model=payload.model,
            category=payload.category,
            lifecycle_status=payload.lifecycle_status.value,
            identity_evidence_ids_json=payload.identity_evidence_ids,
            created_at=now,
            updated_at=now,
        )
        model.capability_claims = [
            self._claim_model(project_id, model.catalog_device_id, item, now)
            for item in payload.capabilities
        ]
        try:
            await self.repository.add_catalog_device(model)
            await self.project_repository.add_event(
                self._event(
                    project_id,
                    "device_catalog_created",
                    {
                        "catalog_device_id": model.catalog_device_id,
                        "capability_claim_count": len(model.capability_claims),
                    },
                    now,
                )
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise AppError(
                code="DEVICE_CATALOG_DUPLICATE",
                message="当前项目已存在相同厂商和型号的设备能力记录。",
                status_code=409,
                details={"manufacturer": payload.manufacturer, "model": payload.model},
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(project_id)
        return self._to_catalog_schema(model)

    async def list_catalog_devices(self, project_id: str) -> CatalogDevicePage:
        await self._require_project(project_id)
        models = await self.repository.list_catalog_devices(project_id)
        return CatalogDevicePage(
            items=[self._to_catalog_schema(item) for item in models],
            total=len(models),
        )

    async def get_catalog_device(
        self, project_id: str, catalog_device_id: str
    ) -> CatalogDevice:
        return self._to_catalog_schema(
            await self._require_catalog_device(project_id, catalog_device_id)
        )

    async def replace_catalog_device(
        self,
        project_id: str,
        catalog_device_id: str,
        payload: CatalogDeviceCreate,
    ) -> CatalogDevice:
        model = await self._require_catalog_device(project_id, catalog_device_id)
        await self._validate_evidence(project_id, self._catalog_evidence_ids(payload))
        now = datetime.now(UTC)
        model.manufacturer = payload.manufacturer
        model.product_name = payload.product_name
        model.model = payload.model
        model.category = payload.category
        model.lifecycle_status = payload.lifecycle_status.value
        model.identity_evidence_ids_json = payload.identity_evidence_ids
        model.updated_at = now
        model.capability_claims.clear()
        model.capability_claims.extend(
            self._claim_model(project_id, catalog_device_id, item, now)
            for item in payload.capabilities
        )
        try:
            await self.project_repository.add_event(
                self._event(
                    project_id,
                    "device_catalog_replaced",
                    {
                        "catalog_device_id": catalog_device_id,
                        "capability_claim_count": len(model.capability_claims),
                    },
                    now,
                )
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise AppError(
                code="DEVICE_CATALOG_DUPLICATE",
                message="当前项目已存在相同厂商和型号的设备能力记录。",
                status_code=409,
                details={"manufacturer": payload.manufacturer, "model": payload.model},
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(project_id)
        refreshed = await self._require_catalog_device(project_id, catalog_device_id)
        return self._to_catalog_schema(refreshed)

    async def delete_catalog_device(
        self, project_id: str, catalog_device_id: str
    ) -> None:
        model = await self._require_catalog_device(project_id, catalog_device_id)
        reference_count = await self.repository.count_household_references(catalog_device_id)
        if reference_count:
            raise AppError(
                code="DEVICE_CATALOG_IN_USE",
                message="设备能力记录仍被家庭快照引用，不能删除。",
                status_code=409,
                details={
                    "catalog_device_id": catalog_device_id,
                    "household_reference_count": reference_count,
                },
            )
        now = datetime.now(UTC)
        try:
            await self.repository.delete_catalog_device(model)
            await self.project_repository.add_event(
                self._event(
                    project_id,
                    "device_catalog_deleted",
                    {"catalog_device_id": catalog_device_id},
                    now,
                )
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(project_id)

    async def replace_household_snapshot(
        self, project_id: str, payload: HouseholdSnapshotCreate
    ) -> HouseholdSnapshot:
        await self._require_project(project_id)
        catalog_device_ids = {
            item.catalog_device_id
            for item in payload.devices
            if item.catalog_device_id is not None
        }
        catalog = {
            item.catalog_device_id: item
            for item in await self.repository.list_catalog_devices(project_id)
        }
        unknown_catalog_ids = sorted(catalog_device_ids - set(catalog))
        if unknown_catalog_ids:
            raise AppError(
                code="HOUSEHOLD_CATALOG_DEVICE_NOT_FOUND",
                message="家庭设备引用了当前项目中不存在的设备目录记录。",
                status_code=422,
                details={"catalog_device_ids": unknown_catalog_ids},
            )
        relation_evidence_ids = {
            evidence_id
            for relation in payload.relations
            for evidence_id in relation.evidence_ids
        }
        await self._validate_evidence(project_id, relation_evidence_ids)
        now = datetime.now(UTC)
        version = await self.repository.next_snapshot_version(project_id)
        snapshot = HouseholdSnapshotModel(
            snapshot_id=f"snapshot_{uuid4().hex[:16]}",
            project_id=project_id,
            version=version,
            status="active",
            authorization_confirmed=True,
            authorized_by=payload.authorized_by,
            purpose=payload.purpose,
            locations_json=[item.model_dump(mode="json") for item in payload.locations],
            created_at=now,
        )
        snapshot.devices = [
            HouseholdDeviceModel(
                household_device_record_id=f"home_record_{uuid4().hex[:16]}",
                household_device_id=item.household_device_id,
                snapshot_id=snapshot.snapshot_id,
                project_id=project_id,
                catalog_device_id=item.catalog_device_id,
                display_name=item.display_name,
                category=item.category,
                model=item.model,
                location_id=item.location_id,
                runtime_status=item.runtime_status.value,
                authorization_status=item.authorization_status.value,
                created_at=now,
            )
            for item in payload.devices
        ]
        snapshot.relations = [
            HouseholdDeviceRelationModel(
                relation_record_id=f"relation_record_{uuid4().hex[:12]}",
                relation_id=item.relation_id,
                snapshot_id=snapshot.snapshot_id,
                project_id=project_id,
                source_household_device_id=item.source_household_device_id,
                target_household_device_id=item.target_household_device_id,
                relation_type=item.relation_type.value,
                verification_status=item.verification_status.value,
                evidence_ids_json=item.evidence_ids,
                created_at=now,
            )
            for item in payload.relations
        ]
        try:
            await self.repository.supersede_current_snapshot(project_id)
            await self.repository.add_snapshot(snapshot)
            await self.project_repository.add_event(
                self._event(
                    project_id,
                    "household_device_snapshot_saved",
                    {
                        "snapshot_id": snapshot.snapshot_id,
                        "version": version,
                        "device_count": len(snapshot.devices),
                        "relation_count": len(snapshot.relations),
                        "authorized_by": payload.authorized_by,
                    },
                    now,
                )
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise AppError(
                code="HOUSEHOLD_SNAPSHOT_CONFLICT",
                message="家庭设备快照发生并发版本冲突，请重新读取后再提交。",
                status_code=409,
                details={"retryable": True},
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(project_id)
        current = await self.repository.get_current_snapshot(project_id)
        if current is None:
            raise RuntimeError("active household snapshot was not persisted")
        return self._to_snapshot_schema(current)

    async def get_household_snapshot(self, project_id: str) -> HouseholdSnapshot:
        await self._require_project(project_id)
        return self._to_snapshot_schema(await self._require_snapshot(project_id))

    async def query_capabilities(
        self, project_id: str, payload: DeviceCapabilityQuery
    ) -> DeviceCapabilityQueryResult:
        await self._require_project(project_id)
        snapshot = await self._require_snapshot(project_id)
        referenced_evidence_ids = {
            evidence_id
            for device in snapshot.devices
            if device.catalog_device is not None
            for evidence_id in (
                list(device.catalog_device.identity_evidence_ids_json)
                + [
                    claim_evidence_id
                    for claim in device.catalog_device.capability_claims
                    for claim_evidence_id in claim.evidence_ids_json
                ]
            )
        }
        current_evidence = await self.repository.get_evidence_by_ids(
            project_id, referenced_evidence_ids
        )
        eligible_evidence_ids = {
            item.evidence_id
            for item in current_evidence
            if item.status in _ELIGIBLE_EVIDENCE_STATUSES
        }
        results = [
            self._evaluate_requirement(
                snapshot.devices,
                requirement,
                eligible_evidence_ids=eligible_evidence_ids,
            )
            for requirement in payload.requirements
        ]
        cited_evidence_ids = sorted(
            {
                evidence_id
                for result in results
                for match in result.matches
                for evidence_id in match.evidence_ids
            }
        )
        return DeviceCapabilityQueryResult(
            project_id=project_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_version=snapshot.version,
            overall_status=self._overall_status(results),
            requirements=results,
            cited_evidence_ids=cited_evidence_ids,
        )

    def _evaluate_requirement(
        self,
        household_devices: list[HouseholdDeviceModel],
        requirement: DeviceCapabilityRequirement,
        *,
        eligible_evidence_ids: set[str],
    ) -> DeviceCapabilityRequirementResult:
        candidates = [
            item
            for item in household_devices
            if requirement.location_id is None or item.location_id == requirement.location_id
        ]
        issues: set[str] = set()
        statuses: list[CapabilityQueryStatus] = []
        matches: list[DeviceCapabilityMatch] = []
        if not candidates:
            issues.add("NO_HOUSEHOLD_DEVICE_AT_LOCATION")
        for device in candidates:
            if device.catalog_device is None:
                issues.add("UNMAPPED_HOUSEHOLD_DEVICE")
                statuses.append(CapabilityQueryStatus.UNKNOWN)
                continue
            if not set(device.catalog_device.identity_evidence_ids_json).issubset(
                eligible_evidence_ids
            ):
                issues.add("DEVICE_IDENTITY_EVIDENCE_STALE")
                statuses.append(CapabilityQueryStatus.UNKNOWN)
                continue
            matching_claims = [
                item
                for item in device.catalog_device.capability_claims
                if item.capability_key == requirement.capability_key
                and (requirement.kind is None or item.kind == requirement.kind.value)
            ]
            claims = [
                item
                for item in matching_claims
                if set(item.evidence_ids_json).issubset(eligible_evidence_ids)
            ]
            if len(claims) != len(matching_claims):
                issues.add("CAPABILITY_EVIDENCE_STALE")
            if not claims:
                issues.add(
                    "CAPABILITY_NOT_DECLARED"
                    if not matching_claims
                    else "CAPABILITY_HAS_NO_CURRENT_EVIDENCE"
                )
                statuses.append(CapabilityQueryStatus.UNKNOWN)
                continue
            status, device_issues = self._evaluate_device_claims(device, claims)
            statuses.append(status)
            issues.update(device_issues)
            matches.append(
                DeviceCapabilityMatch(
                    household_device_id=device.household_device_id,
                    catalog_device_id=device.catalog_device_id or "",
                    display_name=device.display_name,
                    location_id=device.location_id,
                    capability_claim_ids=sorted(
                        {item.capability_claim_id for item in claims}
                    ),
                    evidence_ids=sorted(
                        {
                            evidence_id
                            for item in claims
                            for evidence_id in item.evidence_ids_json
                        }
                    ),
                )
            )
        return DeviceCapabilityRequirementResult(
            requirement=requirement,
            status=self._requirement_status(statuses),
            matches=matches,
            issues=sorted(issues),
        )

    @staticmethod
    def _evaluate_device_claims(
        device: HouseholdDeviceModel,
        claims: list[DeviceCapabilityClaimModel],
    ) -> tuple[CapabilityQueryStatus, set[str]]:
        issues: set[str] = set()
        assertions = {item.assertion for item in claims}
        if {
            CapabilityAssertion.SUPPORTED.value,
            CapabilityAssertion.UNSUPPORTED.value,
        }.issubset(assertions):
            return CapabilityQueryStatus.CONFLICT, {"CONFLICTING_CAPABILITY_EVIDENCE"}
        supported = [
            item for item in claims if item.assertion == CapabilityAssertion.SUPPORTED.value
        ]
        if not supported:
            if CapabilityAssertion.UNSUPPORTED.value in assertions:
                return CapabilityQueryStatus.UNAVAILABLE, {"CAPABILITY_UNSUPPORTED"}
            return CapabilityQueryStatus.UNKNOWN, {"CAPABILITY_ASSERTION_UNKNOWN"}
        availability_values = {item.availability for item in supported}
        if {
            CapabilityAvailability.AVAILABLE.value,
            CapabilityAvailability.UNAVAILABLE.value,
        }.issubset(availability_values):
            return CapabilityQueryStatus.CONFLICT, {"CONFLICTING_AVAILABILITY_EVIDENCE"}
        if device.authorization_status == HouseholdAuthorizationStatus.DENIED.value:
            return CapabilityQueryStatus.UNAVAILABLE, {"DEVICE_AUTHORIZATION_DENIED"}
        if (
            device.authorization_status == HouseholdAuthorizationStatus.UNKNOWN.value
            and any(item.authorization_required for item in supported)
        ):
            return CapabilityQueryStatus.UNKNOWN, {"DEVICE_AUTHORIZATION_UNKNOWN"}
        if device.runtime_status == HouseholdRuntimeStatus.UNKNOWN.value:
            return CapabilityQueryStatus.UNKNOWN, {"DEVICE_RUNTIME_UNKNOWN"}
        if device.runtime_status == HouseholdRuntimeStatus.OFFLINE.value:
            offline_values = {item.offline_support for item in supported}
            if OfflineSupport.FULL.value in offline_values:
                pass
            elif OfflineSupport.DEGRADED.value in offline_values:
                issues.add("DEVICE_OFFLINE_DEGRADED")
            elif OfflineSupport.UNKNOWN.value in offline_values:
                return CapabilityQueryStatus.UNKNOWN, {"OFFLINE_SUPPORT_UNKNOWN"}
            else:
                return CapabilityQueryStatus.UNAVAILABLE, {"DEVICE_OFFLINE_NO_FALLBACK"}
        if CapabilityAvailability.AVAILABLE.value in availability_values:
            return CapabilityQueryStatus.AVAILABLE, issues
        if CapabilityAvailability.UNKNOWN.value in availability_values:
            return CapabilityQueryStatus.UNKNOWN, issues | {"CAPABILITY_AVAILABILITY_UNKNOWN"}
        return CapabilityQueryStatus.UNAVAILABLE, issues | {"CAPABILITY_UNAVAILABLE"}

    @staticmethod
    def _requirement_status(
        statuses: list[CapabilityQueryStatus],
    ) -> CapabilityQueryStatus:
        if CapabilityQueryStatus.CONFLICT in statuses:
            return CapabilityQueryStatus.CONFLICT
        if CapabilityQueryStatus.AVAILABLE in statuses:
            return CapabilityQueryStatus.AVAILABLE
        if CapabilityQueryStatus.UNKNOWN in statuses or not statuses:
            return CapabilityQueryStatus.UNKNOWN
        return CapabilityQueryStatus.UNAVAILABLE

    @staticmethod
    def _overall_status(
        results: list[DeviceCapabilityRequirementResult],
    ) -> CapabilityQueryStatus:
        statuses = {item.status for item in results}
        if CapabilityQueryStatus.CONFLICT in statuses:
            return CapabilityQueryStatus.CONFLICT
        if CapabilityQueryStatus.UNAVAILABLE in statuses:
            return CapabilityQueryStatus.UNAVAILABLE
        if CapabilityQueryStatus.UNKNOWN in statuses:
            return CapabilityQueryStatus.UNKNOWN
        return CapabilityQueryStatus.AVAILABLE

    async def _require_project(self, project_id: str) -> None:
        if await self.repository.get_project(project_id) is None:
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="没有找到指定的研究项目。",
                status_code=404,
                details={"project_id": project_id},
            )

    async def _require_catalog_device(
        self, project_id: str, catalog_device_id: str
    ) -> DeviceCatalogModel:
        await self._require_project(project_id)
        model = await self.repository.get_catalog_device(project_id, catalog_device_id)
        if model is None:
            raise AppError(
                code="DEVICE_CATALOG_NOT_FOUND",
                message="没有找到指定的设备能力记录。",
                status_code=404,
                details={"catalog_device_id": catalog_device_id},
            )
        return model

    async def _require_snapshot(self, project_id: str) -> HouseholdSnapshotModel:
        snapshot = await self.repository.get_current_snapshot(project_id)
        if snapshot is None:
            raise AppError(
                code="HOUSEHOLD_SNAPSHOT_NOT_FOUND",
                message="尚未保存用户授权的家庭设备快照。",
                status_code=404,
                details={"project_id": project_id},
            )
        return snapshot

    async def _validate_evidence(
        self, project_id: str, evidence_ids: set[str]
    ) -> None:
        if not evidence_ids:
            return
        models = await self.repository.get_evidence_by_ids(project_id, evidence_ids)
        by_id = {item.evidence_id: item for item in models}
        missing = sorted(evidence_ids - set(by_id))
        ineligible = {
            evidence_id: model.status
            for evidence_id, model in by_id.items()
            if model.status not in _ELIGIBLE_EVIDENCE_STATUSES
        }
        if missing or ineligible:
            raise AppError(
                code="DEVICE_CAPABILITY_EVIDENCE_INVALID",
                message="设备能力只能绑定当前项目已核验或部分核验的 Evidence。",
                status_code=422,
                details={
                    "missing_or_cross_project_evidence_ids": missing,
                    "ineligible_evidence_statuses": ineligible,
                },
            )

    @staticmethod
    def _catalog_evidence_ids(payload: CatalogDeviceCreate) -> set[str]:
        return set(payload.identity_evidence_ids) | {
            evidence_id
            for capability in payload.capabilities
            for evidence_id in capability.evidence_ids
        }

    @staticmethod
    def _claim_model(
        project_id: str,
        catalog_device_id: str,
        payload: DeviceCapabilityClaimInput,
        now: datetime,
    ) -> DeviceCapabilityClaimModel:
        return DeviceCapabilityClaimModel(
            capability_claim_id=f"cap_{uuid4().hex[:16]}",
            project_id=project_id,
            catalog_device_id=catalog_device_id,
            capability_key=payload.capability_key,
            capability_name=payload.capability_name,
            kind=payload.kind.value,
            assertion=payload.assertion.value,
            availability=payload.availability.value,
            confidence=payload.confidence,
            evidence_ids_json=payload.evidence_ids,
            latency_ms_max=payload.latency_ms_max,
            data_scope=payload.data_scope.value,
            authorization_required=payload.authorization_required,
            offline_support=payload.offline_support.value,
            fallback=payload.fallback,
            created_at=now,
        )

    @staticmethod
    def _to_catalog_schema(model: DeviceCatalogModel) -> CatalogDevice:
        return CatalogDevice(
            catalog_device_id=model.catalog_device_id,
            project_id=model.project_id,
            manufacturer=model.manufacturer,
            product_name=model.product_name,
            model=model.model,
            category=model.category,
            lifecycle_status=DeviceLifecycleStatus(model.lifecycle_status),
            identity_evidence_ids=list(model.identity_evidence_ids_json),
            capabilities=[
                DeviceCapabilityClaim(
                    capability_claim_id=item.capability_claim_id,
                    capability_key=item.capability_key,
                    capability_name=item.capability_name,
                    kind=DeviceCapabilityKind(item.kind),
                    assertion=CapabilityAssertion(item.assertion),
                    availability=CapabilityAvailability(item.availability),
                    confidence=item.confidence,
                    evidence_ids=list(item.evidence_ids_json),
                    latency_ms_max=item.latency_ms_max,
                    data_scope=DeviceDataScope(item.data_scope),
                    authorization_required=item.authorization_required,
                    offline_support=OfflineSupport(item.offline_support),
                    fallback=item.fallback,
                )
                for item in model.capability_claims
            ],
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_snapshot_schema(model: HouseholdSnapshotModel) -> HouseholdSnapshot:
        return HouseholdSnapshot(
            snapshot_id=model.snapshot_id,
            project_id=model.project_id,
            version=model.version,
            status="active",
            authorization_confirmed=True,
            authorized_by=model.authorized_by,
            purpose=model.purpose,
            locations=[
                HouseholdLocationInput.model_validate(item) for item in model.locations_json
            ],
            devices=[
                HouseholdDeviceInput(
                    household_device_id=item.household_device_id,
                    catalog_device_id=item.catalog_device_id,
                    display_name=item.display_name,
                    category=item.category,
                    model=item.model,
                    location_id=item.location_id,
                    runtime_status=HouseholdRuntimeStatus(item.runtime_status),
                    authorization_status=HouseholdAuthorizationStatus(
                        item.authorization_status
                    ),
                )
                for item in model.devices
            ],
            relations=[
                HouseholdDeviceRelationInput(
                    relation_id=item.relation_id,
                    source_household_device_id=item.source_household_device_id,
                    target_household_device_id=item.target_household_device_id,
                    relation_type=DeviceRelationType(item.relation_type),
                    verification_status=RelationVerificationStatus(
                        item.verification_status
                    ),
                    evidence_ids=list(item.evidence_ids_json),
                )
                for item in model.relations
            ],
            created_at=model.created_at,
        )

    def _event(
        self,
        project_id: str,
        event_type: str,
        data: dict[str, object],
        now: datetime,
    ) -> ProjectEventModel:
        return ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type=event_type,
            data_json=data,
            trace_id=self.trace_id,
            created_at=now,
        )
