from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.application.runtime.contracts import AgentInvocation
from app.schemas.runtime import RuntimeCapability


@dataclass(frozen=True)
class CliWorkspace:
    root: Path
    input_dir: Path
    output_dir: Path
    state_dir: Path
    logs_dir: Path
    invocation_path: Path


@dataclass(frozen=True)
class CliCommand:
    executable: str
    arguments: tuple[str, ...]
    environment: Mapping[str, str]


@dataclass(frozen=True)
class CliProbeResult:
    executable_available: bool
    version: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CliProcessResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_seconds: float


class ExternalCliDriver(Protocol):
    @property
    def runtime_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def adapter_type(self) -> str: ...

    @property
    def enabled(self) -> bool: ...

    @property
    def executable(self) -> str: ...

    @property
    def credential_env(self) -> str: ...

    @property
    def model_id(self) -> str | None: ...

    @property
    def capabilities(self) -> tuple[RuntimeCapability, ...]: ...

    def version_arguments(self) -> tuple[str, ...]: ...

    def prepare(
        self,
        invocation: AgentInvocation,
        workspace: CliWorkspace,
        credential: str,
    ) -> CliCommand: ...

    def decode_output(self, stdout: bytes) -> object: ...
