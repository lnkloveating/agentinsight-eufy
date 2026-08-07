import asyncio
import sys
from pathlib import Path

import pytest

from app.application.runtime.cli_process import (
    CliOutputLimitError,
    ExternalCliProcessRunner,
)
from app.application.runtime.contracts import CancellationToken, RuntimeCancellationError


@pytest.mark.asyncio
async def test_process_runner_executes_without_inheriting_unapproved_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UNAPPROVED_TEST_SECRET", "must-not-leak")
    runner = ExternalCliProcessRunner(
        max_output_bytes=4096, probe_timeout_seconds=2
    )
    result = await runner.run(
        executable=sys.executable,
        arguments=(
            "-c",
            "import os; print(os.environ.get('UNAPPROVED_TEST_SECRET', 'missing')); "
            "print(os.environ['APPROVED_TEST_VALUE'])",
        ),
        cwd=tmp_path,
        environment={"APPROVED_TEST_VALUE": "visible"},
        timeout_seconds=2,
        cancellation_token=CancellationToken(),
    )

    assert result.exit_code == 0
    assert result.stdout.decode().splitlines() == ["missing", "visible"]


@pytest.mark.asyncio
async def test_process_runner_enforces_output_limit_and_timeout(tmp_path: Path) -> None:
    runner = ExternalCliProcessRunner(max_output_bytes=1024, probe_timeout_seconds=2)
    with pytest.raises(CliOutputLimitError):
        await runner.run(
            executable=sys.executable,
            arguments=("-c", "print('x' * 4096)"),
            cwd=tmp_path,
            environment={},
            timeout_seconds=2,
            cancellation_token=CancellationToken(),
        )

    with pytest.raises(TimeoutError):
        await runner.run(
            executable=sys.executable,
            arguments=("-c", "import time; time.sleep(10)"),
            cwd=tmp_path,
            environment={},
            timeout_seconds=0.05,
            cancellation_token=CancellationToken(),
        )


@pytest.mark.asyncio
async def test_process_runner_terminates_when_token_is_cancelled(tmp_path: Path) -> None:
    runner = ExternalCliProcessRunner(max_output_bytes=4096, probe_timeout_seconds=2)
    token = CancellationToken()
    execution = asyncio.create_task(
        runner.run(
            executable=sys.executable,
            arguments=("-c", "import time; time.sleep(10)"),
            cwd=tmp_path,
            environment={},
            timeout_seconds=5,
            cancellation_token=token,
        )
    )
    await asyncio.sleep(0.05)
    token.cancel()

    with pytest.raises(RuntimeCancellationError):
        await execution


@pytest.mark.asyncio
async def test_probe_reports_missing_and_available_executables() -> None:
    runner = ExternalCliProcessRunner(max_output_bytes=4096, probe_timeout_seconds=2)
    missing = await runner.probe("agentinsight-missing-cli", ("--version",))
    available = await runner.probe(sys.executable, ("--version",))

    assert missing.executable_available is False
    assert missing.error == "executable_missing"
    assert available.executable_available is True
    assert available.error is None
    assert available.version is not None
