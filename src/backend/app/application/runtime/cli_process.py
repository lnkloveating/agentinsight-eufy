from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.application.runtime.cli_contracts import CliProbeResult, CliProcessResult
from app.application.runtime.contracts import CancellationToken, RuntimeCancellationError


class CliExecutableNotFoundError(FileNotFoundError):
    pass


class CliOutputLimitError(RuntimeError):
    pass


class ExternalCliProcessRunner:
    def __init__(self, *, max_output_bytes: int, probe_timeout_seconds: float) -> None:
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        if probe_timeout_seconds <= 0:
            raise ValueError("probe_timeout_seconds must be positive")
        self.max_output_bytes = max_output_bytes
        self.probe_timeout_seconds = probe_timeout_seconds

    async def probe(
        self, executable: str, version_arguments: tuple[str, ...]
    ) -> CliProbeResult:
        resolved = self.resolve_executable(executable)
        if resolved is None:
            return CliProbeResult(executable_available=False, error="executable_missing")
        token = CancellationToken()
        try:
            result = await self.run(
                executable=resolved,
                arguments=version_arguments,
                cwd=Path.cwd(),
                environment={},
                timeout_seconds=self.probe_timeout_seconds,
                cancellation_token=token,
            )
        except (TimeoutError, CliOutputLimitError, OSError):
            return CliProbeResult(executable_available=True, error="probe_failed")
        if result.exit_code != 0:
            return CliProbeResult(executable_available=True, error="probe_failed")
        version = result.stdout.decode("utf-8", errors="replace").strip()
        if not version:
            version = result.stderr.decode("utf-8", errors="replace").strip()
        return CliProbeResult(
            executable_available=True,
            version=(version.splitlines()[0][:200] if version else None),
            error=None if version else "probe_failed",
        )

    async def run(
        self,
        *,
        executable: str,
        arguments: tuple[str, ...],
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: float,
        cancellation_token: CancellationToken,
    ) -> CliProcessResult:
        resolved = self.resolve_executable(executable)
        if resolved is None:
            raise CliExecutableNotFoundError(executable)
        command, command_arguments = self._launcher(resolved, arguments)
        process_environment = self._base_environment()
        process_environment.update(environment)
        started = time.monotonic()
        if os.name == "nt":
            windows_subprocess: Any = subprocess
            process = await asyncio.create_subprocess_exec(
                command,
                *command_arguments,
                cwd=str(cwd),
                env=process_environment,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=windows_subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                command,
                *command_arguments,
                cwd=str(cwd),
                env=process_environment,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        try:
            stdout, stderr = await asyncio.wait_for(
                self._collect(process, cancellation_token),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            await self._terminate(process)
            raise
        except (asyncio.CancelledError, RuntimeCancellationError, CliOutputLimitError):
            await self._terminate(process)
            raise
        return CliProcessResult(
            exit_code=int(process.returncode or 0),
            stdout=stdout,
            stderr=stderr,
            duration_seconds=time.monotonic() - started,
        )

    async def _collect(
        self,
        process: asyncio.subprocess.Process,
        cancellation_token: CancellationToken,
    ) -> tuple[bytes, bytes]:
        total = [0]
        output_task = asyncio.create_task(
            self._read_outputs(process, total), name="external-cli-output"
        )
        process_task = asyncio.create_task(process.wait(), name="external-cli-process")
        cancellation_task = asyncio.create_task(
            cancellation_token.wait(), name="external-cli-cancellation"
        )
        try:
            while True:
                done, _ = await asyncio.wait(
                    {output_task, process_task, cancellation_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancellation_task in done:
                    raise RuntimeCancellationError("external CLI invocation was cancelled")
                if output_task in done:
                    stdout, stderr = output_task.result()
                    await process_task
                    return stdout, stderr
                if process_task in done:
                    return await output_task
        finally:
            for task in (output_task, process_task, cancellation_task):
                if not task.done():
                    task.cancel()

    async def _read_outputs(
        self, process: asyncio.subprocess.Process, total: list[int]
    ) -> tuple[bytes, bytes]:
        async def read_stream(stream: asyncio.StreamReader | None) -> bytes:
            if stream is None:
                return b""
            chunks: list[bytes] = []
            while chunk := await stream.read(65_536):
                total[0] += len(chunk)
                if total[0] > self.max_output_bytes:
                    raise CliOutputLimitError("external CLI output exceeded configured limit")
                chunks.append(chunk)
            return b"".join(chunks)

        stdout_task = asyncio.create_task(read_stream(process.stdout))
        stderr_task = asyncio.create_task(read_stream(process.stderr))
        try:
            stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
            return stdout, stderr
        finally:
            for task in (stdout_task, stderr_task):
                if not task.done():
                    task.cancel()

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        if os.name == "nt":
            taskkill = shutil.which("taskkill")
            if taskkill is not None:
                killer = await asyncio.create_subprocess_exec(
                    taskkill,
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await killer.wait()
            else:
                process.kill()
        else:
            try:
                os_with_process_groups: Any = os
                os_with_process_groups.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            if process.returncode is None:
                process.kill()
                await process.wait()

    @staticmethod
    def resolve_executable(executable: str) -> str | None:
        stripped = executable.strip()
        if not stripped:
            return None
        if Path(stripped).is_absolute() or any(separator in stripped for separator in ("/", "\\")):
            candidate = Path(stripped).resolve()
            return str(candidate) if candidate.is_file() else None
        return shutil.which(stripped)

    @staticmethod
    def _launcher(
        resolved_executable: str, arguments: tuple[str, ...]
    ) -> tuple[str, tuple[str, ...]]:
        if os.name == "nt" and Path(resolved_executable).suffix.lower() in {".cmd", ".bat"}:
            command_processor = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
            command_line = subprocess.list2cmdline((resolved_executable, *arguments))
            return command_processor, ("/d", "/s", "/c", command_line)
        return resolved_executable, arguments

    @staticmethod
    def _base_environment() -> dict[str, str]:
        allowed = {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "LANG",
            "LC_ALL",
            "SSL_CERT_FILE",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
        }
        return {key: value for key, value in os.environ.items() if key in allowed}


def redact_text(value: bytes, secrets: tuple[str, ...], *, limit: int = 500) -> str:
    text = value.decode("utf-8", errors="replace")[:limit]
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text
