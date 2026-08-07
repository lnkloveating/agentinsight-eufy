"""Agent Runtime Core 的 Adapter、调用和错误契约。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.workflows.contracts import AgentContext, ResearchArtifact, ResearchTask


class RuntimeErrorCode(StrEnum):
    RUNTIME_NOT_BOUND = "runtime_not_bound"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    SCHEMA_INVALID = "schema_invalid"
    ADAPTER_FAILED = "adapter_failed"
    ARTIFACT_INVALID = "artifact_invalid"
    PERMISSION_DENIED = "permission_denied"
    DEPENDENCY_MISSING = "dependency_missing"
    EXECUTABLE_MISSING = "executable_missing"
    CREDENTIAL_MISSING = "credential_missing"
    PROBE_FAILED = "probe_failed"
    PROCESS_FAILED = "process_failed"
    OUTPUT_TOO_LARGE = "output_too_large"


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise RuntimeCancellationError("agent invocation was cancelled")

    async def wait(self) -> None:
        await self._event.wait()


@dataclass(frozen=True)
class AgentInvocation:
    agent_run_id: str
    trace_id: str
    attempt_number: int
    workspace_key: str
    input_artifact_ids: tuple[str, ...]
    task: ResearchTask
    context: AgentContext
    cancellation_token: CancellationToken


class AgentAdapter(Protocol):
    @property
    def adapter_type(self) -> str: ...

    async def execute(self, invocation: AgentInvocation) -> object: ...


@dataclass(frozen=True)
class AdapterBinding:
    agent_type: str
    adapter_type: str
    adapter: AgentAdapter


class RuntimeCancellationError(RuntimeError):
    pass


class RuntimeGatewayError(RuntimeError):
    def __init__(
        self,
        code: RuntimeErrorCode,
        message: str,
        *,
        agent_run_id: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.agent_run_id = agent_run_id
        self.retryable = retryable
        self.details = details or {}
        super().__init__(message)


@dataclass(frozen=True)
class StoredArtifact:
    artifact: ResearchArtifact
    project_id: str
    agent_run_id: str
    version: int
    input_artifact_ids: tuple[str, ...]
    content_hash: str
