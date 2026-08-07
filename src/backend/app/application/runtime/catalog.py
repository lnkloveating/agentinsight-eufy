from __future__ import annotations

from collections.abc import Sequence

from app.application.model_gateway import CredentialResolver
from app.application.runtime.cli_contracts import ExternalCliDriver
from app.application.runtime.cli_process import ExternalCliProcessRunner
from app.schemas.runtime import (
    ExternalRuntimePage,
    ExternalRuntimeSummary,
    RuntimeUnavailableReason,
)


class ExternalRuntimeCatalog:
    def __init__(
        self,
        drivers: Sequence[ExternalCliDriver],
        credentials: CredentialResolver,
        process_runner: ExternalCliProcessRunner,
    ) -> None:
        runtime_ids: set[str] = set()
        for driver in drivers:
            if driver.runtime_id in runtime_ids:
                raise ValueError(f"duplicate external runtime id: {driver.runtime_id}")
            runtime_ids.add(driver.runtime_id)
        self.drivers = tuple(drivers)
        self.credentials = credentials
        self.process_runner = process_runner

    async def public_page(self) -> ExternalRuntimePage:
        items = [await self._summary(driver) for driver in self.drivers]
        return ExternalRuntimePage(items=sorted(items, key=lambda item: item.runtime_id))

    async def _summary(self, driver: ExternalCliDriver) -> ExternalRuntimeSummary:
        credential_available = self.credentials.available(driver.credential_env)
        if not driver.enabled:
            return self._unavailable(
                driver,
                credential_available=credential_available,
                executable_available=False,
                reason=RuntimeUnavailableReason.DISABLED,
            )
        probe = await self.process_runner.probe(
            driver.executable, driver.version_arguments()
        )
        if not probe.executable_available:
            return self._unavailable(
                driver,
                credential_available=credential_available,
                executable_available=False,
                reason=RuntimeUnavailableReason.EXECUTABLE_MISSING,
            )
        if probe.error is not None:
            return self._unavailable(
                driver,
                credential_available=credential_available,
                executable_available=True,
                reason=RuntimeUnavailableReason.PROBE_FAILED,
            )
        if not credential_available:
            return self._unavailable(
                driver,
                credential_available=False,
                executable_available=True,
                reason=RuntimeUnavailableReason.CREDENTIAL_MISSING,
                version=probe.version,
            )
        return ExternalRuntimeSummary(
            runtime_id=driver.runtime_id,
            display_name=driver.display_name,
            capabilities=list(driver.capabilities),
            enabled=True,
            executable_available=True,
            credential_available=True,
            available=True,
            version=probe.version,
            unavailable_reason=None,
            model_id=driver.model_id,
        )

    @staticmethod
    def _unavailable(
        driver: ExternalCliDriver,
        *,
        credential_available: bool,
        executable_available: bool,
        reason: RuntimeUnavailableReason,
        version: str | None = None,
    ) -> ExternalRuntimeSummary:
        return ExternalRuntimeSummary(
            runtime_id=driver.runtime_id,
            display_name=driver.display_name,
            capabilities=list(driver.capabilities),
            enabled=driver.enabled,
            executable_available=executable_available,
            credential_available=credential_available,
            available=False,
            version=version,
            unavailable_reason=reason,
            model_id=driver.model_id,
        )
