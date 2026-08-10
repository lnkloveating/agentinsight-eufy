"""设备能力图的项目隔离持久化查询。"""

from typing import cast

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    DeviceCatalogModel,
    EvidenceModel,
    HouseholdDeviceModel,
    HouseholdSnapshotModel,
    ProjectModel,
)


class DeviceCapabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> ProjectModel | None:
        return await self.session.get(ProjectModel, project_id)

    async def get_catalog_device(
        self, project_id: str, catalog_device_id: str
    ) -> DeviceCatalogModel | None:
        statement = (
            select(DeviceCatalogModel)
            .where(
                DeviceCatalogModel.project_id == project_id,
                DeviceCatalogModel.catalog_device_id == catalog_device_id,
            )
            .options(selectinload(DeviceCatalogModel.capability_claims))
        )
        return cast(DeviceCatalogModel | None, await self.session.scalar(statement))

    async def list_catalog_devices(self, project_id: str) -> list[DeviceCatalogModel]:
        statement: Select[tuple[DeviceCatalogModel]] = (
            select(DeviceCatalogModel)
            .where(DeviceCatalogModel.project_id == project_id)
            .options(selectinload(DeviceCatalogModel.capability_claims))
            .order_by(
                DeviceCatalogModel.manufacturer.asc(),
                DeviceCatalogModel.model.asc(),
            )
        )
        return list(await self.session.scalars(statement))

    async def add_catalog_device(self, model: DeviceCatalogModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def delete_catalog_device(self, model: DeviceCatalogModel) -> None:
        await self.session.delete(model)
        await self.session.flush()

    async def count_household_references(self, catalog_device_id: str) -> int:
        statement = select(func.count()).select_from(HouseholdDeviceModel).where(
            HouseholdDeviceModel.catalog_device_id == catalog_device_id
        )
        return int(await self.session.scalar(statement) or 0)

    async def get_evidence_by_ids(
        self, project_id: str, evidence_ids: set[str]
    ) -> list[EvidenceModel]:
        if not evidence_ids:
            return []
        statement = select(EvidenceModel).where(
            EvidenceModel.project_id == project_id,
            EvidenceModel.evidence_id.in_(evidence_ids),
        )
        return list(await self.session.scalars(statement))

    async def get_current_snapshot(self, project_id: str) -> HouseholdSnapshotModel | None:
        statement = (
            select(HouseholdSnapshotModel)
            .where(
                HouseholdSnapshotModel.project_id == project_id,
                HouseholdSnapshotModel.status == "active",
            )
            .options(
                selectinload(HouseholdSnapshotModel.devices)
                .selectinload(HouseholdDeviceModel.catalog_device)
                .selectinload(DeviceCatalogModel.capability_claims),
                selectinload(HouseholdSnapshotModel.relations),
            )
            .order_by(HouseholdSnapshotModel.version.desc())
        )
        return cast(HouseholdSnapshotModel | None, await self.session.scalar(statement))

    async def next_snapshot_version(self, project_id: str) -> int:
        statement = select(func.coalesce(func.max(HouseholdSnapshotModel.version), 0)).where(
            HouseholdSnapshotModel.project_id == project_id
        )
        return int(await self.session.scalar(statement) or 0) + 1

    async def supersede_current_snapshot(self, project_id: str) -> None:
        await self.session.execute(
            update(HouseholdSnapshotModel)
            .where(
                HouseholdSnapshotModel.project_id == project_id,
                HouseholdSnapshotModel.status == "active",
            )
            .values(status="superseded")
        )

    async def add_snapshot(self, model: HouseholdSnapshotModel) -> None:
        self.session.add(model)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
