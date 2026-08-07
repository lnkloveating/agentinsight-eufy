from __future__ import annotations

from pathlib import Path

from app.application.model_gateway import CredentialResolver
from app.application.runtime.cli_contracts import ExternalCliDriver
from app.application.runtime.cli_process import (
    CliExecutableNotFoundError,
    CliOutputLimitError,
    ExternalCliProcessRunner,
    redact_text,
)
from app.application.runtime.contracts import (
    AgentInvocation,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.application.runtime.external_workspace import ExternalCliWorkspaceManager
from app.application.runtime.opencode_driver import ExternalCliOutputError


class ExternalCliAgentAdapter:
    adapter_type = "external_cli"

    def __init__(
        self,
        driver: ExternalCliDriver,
        credentials: CredentialResolver,
        process_runner: ExternalCliProcessRunner,
        workspace_root: Path,
    ) -> None:
        self.driver = driver
        self.credentials = credentials
        self.process_runner = process_runner
        self.workspaces = ExternalCliWorkspaceManager(workspace_root)

    async def execute(self, invocation: AgentInvocation) -> object:
        invocation.cancellation_token.raise_if_cancelled()
        if not self.driver.enabled:
            raise self._error(
                invocation,
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "External CLI runtime is disabled.",
                retryable=False,
                details={"reason": "disabled", "runtime_id": self.driver.runtime_id},
            )

        credential = self.credentials.resolve(self.driver.credential_env)
        if credential is None:
            raise self._error(
                invocation,
                RuntimeErrorCode.CREDENTIAL_MISSING,
                "External CLI runtime credential is unavailable.",
                retryable=False,
                details={"runtime_id": self.driver.runtime_id},
            )

        probe = await self.process_runner.probe(
            self.driver.executable, self.driver.version_arguments()
        )
        if not probe.executable_available:
            raise self._error(
                invocation,
                RuntimeErrorCode.EXECUTABLE_MISSING,
                "External CLI executable is unavailable.",
                retryable=False,
                details={"runtime_id": self.driver.runtime_id},
            )
        if probe.error is not None:
            raise self._error(
                invocation,
                RuntimeErrorCode.PROBE_FAILED,
                "External CLI health probe failed.",
                retryable=True,
                details={"runtime_id": self.driver.runtime_id},
            )

        workspace = self.workspaces.prepare(invocation)
        command = self.driver.prepare(invocation, workspace, credential)
        try:
            result = await self.process_runner.run(
                executable=command.executable,
                arguments=command.arguments,
                cwd=workspace.root,
                environment=command.environment,
                timeout_seconds=float(invocation.task.budget.deadline_seconds),
                cancellation_token=invocation.cancellation_token,
            )
        except CliExecutableNotFoundError as exc:
            raise self._error(
                invocation,
                RuntimeErrorCode.EXECUTABLE_MISSING,
                "External CLI executable disappeared before execution.",
                retryable=True,
                details={"runtime_id": self.driver.runtime_id},
            ) from exc
        except CliOutputLimitError as exc:
            raise self._error(
                invocation,
                RuntimeErrorCode.OUTPUT_TOO_LARGE,
                "External CLI output exceeded the configured limit.",
                retryable=False,
                details={"runtime_id": self.driver.runtime_id},
            ) from exc

        self.workspaces.write_process_metadata(
            workspace,
            runtime_id=self.driver.runtime_id,
            exit_code=result.exit_code,
            stdout_bytes=len(result.stdout),
            stderr_bytes=len(result.stderr),
            duration_seconds=result.duration_seconds,
        )
        if result.exit_code != 0:
            raise self._error(
                invocation,
                RuntimeErrorCode.PROCESS_FAILED,
                "External CLI process exited unsuccessfully.",
                retryable=True,
                details={
                    "runtime_id": self.driver.runtime_id,
                    "exit_code": result.exit_code,
                    "stderr": redact_text(result.stderr, (credential,)),
                },
            )
        invocation.cancellation_token.raise_if_cancelled()
        try:
            output = self.driver.decode_output(result.stdout)
        except (ExternalCliOutputError, UnicodeDecodeError, ValueError) as exc:
            raise self._error(
                invocation,
                RuntimeErrorCode.SCHEMA_INVALID,
                "External CLI output is not a valid ResearchArtifact.",
                retryable=False,
                details={"runtime_id": self.driver.runtime_id},
            ) from exc
        self.workspaces.write_output(workspace, output)
        return output

    @staticmethod
    def _error(
        invocation: AgentInvocation,
        code: RuntimeErrorCode,
        message: str,
        *,
        retryable: bool,
        details: dict[str, object],
    ) -> RuntimeGatewayError:
        return RuntimeGatewayError(
            code,
            message,
            agent_run_id=invocation.agent_run_id,
            retryable=retryable,
            details=details,
        )
