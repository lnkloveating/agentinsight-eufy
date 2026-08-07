from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

from app.application.runtime.cli_contracts import CliWorkspace
from app.application.runtime.contracts import AgentInvocation
from app.workflows.contracts import ResearchArtifact

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class ExternalCliWorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def prepare(self, invocation: AgentInvocation) -> CliWorkspace:
        project_component = self._component(invocation.task.project_id)
        run_component = self._component(invocation.agent_run_id)
        workspace_root = (self.root / project_component / run_component).resolve()
        if self.root not in workspace_root.parents:
            raise ValueError("runtime workspace escaped configured root")

        input_dir = workspace_root / "input"
        output_dir = workspace_root / "output"
        state_dir = workspace_root / "state"
        logs_dir = workspace_root / "logs"
        for directory in (input_dir, output_dir, state_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=False)

        invocation_path = input_dir / "invocation.json"
        invocation_path.write_text(
            json.dumps(self._invocation_payload(invocation), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return CliWorkspace(
            root=workspace_root,
            input_dir=input_dir,
            output_dir=output_dir,
            state_dir=state_dir,
            logs_dir=logs_dir,
            invocation_path=invocation_path,
        )

    @staticmethod
    def write_process_metadata(
        workspace: CliWorkspace,
        *,
        runtime_id: str,
        exit_code: int,
        stdout_bytes: int,
        stderr_bytes: int,
        duration_seconds: float,
    ) -> None:
        payload = {
            "runtime_id": runtime_id,
            "exit_code": exit_code,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "duration_seconds": round(duration_seconds, 6),
        }
        (workspace.logs_dir / "process.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def write_output(workspace: CliWorkspace, output: object) -> None:
        (workspace.output_dir / "research_artifact.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _component(value: str) -> str:
        if _SAFE_COMPONENT.fullmatch(value):
            return value
        return f"id_{sha256(value.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _invocation_payload(invocation: AgentInvocation) -> dict[str, object]:
        return {
            "agent_run_id": invocation.agent_run_id,
            "trace_id": invocation.trace_id,
            "attempt_number": invocation.attempt_number,
            "input_artifact_ids": list(invocation.input_artifact_ids),
            "task": invocation.task.model_dump(mode="json"),
            "context": invocation.context.model_dump(mode="json"),
            "output_schema": ResearchArtifact.model_json_schema(),
        }
